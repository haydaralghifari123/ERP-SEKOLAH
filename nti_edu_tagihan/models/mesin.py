# -*- coding: utf-8 -*-
import calendar
import contextvars
import logging
from contextlib import contextmanager
from datetime import timedelta

import psycopg2
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models, modules, tools
from odoo.exceptions import UserError
from odoo.tools import float_round

_logger = logging.getLogger(__name__)

GRUP_BENDAHARA = 'nti_edu_tagihan.group_tagihan_bendahara'

# Penanda "payment ini dibuat `_bayar_baris`" untuk wizard pembayaran Odoo. Sengaja bukan kunci konteks Odoo yang bisa
# dikirim bebas lewat RPC; ContextVar hanya bisa dipasang kode server.
_BAYAR_TAGIHAN = contextvars.ContextVar('nti_edu_bayar_tagihan', default=False)


@contextmanager
def _bayar_tagihan():
    token = _BAYAR_TAGIHAN.set(True)
    try:
        yield
    finally:
        _BAYAR_TAGIHAN.reset(token)


def _bulatkan_satuan(mata_uang, nilai):
    """Bulatkan ke satuan utuh mata uang (rupiah, spec §4.2); mata uang yang pembulatannya sudah ≥ 1 memakai
    pembulatannya sendiri."""
    if mata_uang.rounding >= 1:
        return mata_uang.round(nilai)
    return float_round(nilai, precision_digits=0)


def _boleh_commit():
    """Idiom Odoo 18 (`account.move._can_commit`): commit hanya di luar tes."""
    return not tools.config['test_enable'] and not modules.module.current_test


def _awal_bulan(tanggal):
    return tanggal.replace(day=1)


def _tanggal_dalam_bulan(bulan, hari):
    """Tanggal ke-`hari` pada bulan `bulan`, dipangkas ke akhir bulan."""
    return bulan.replace(day=min(hari, calendar.monthrange(bulan.year, bulan.month)[1]))


def _jumlah_bulan(dari, sampai):
    """Banyak bulan kalender dari bulan `dari` sampai bulan `sampai`, keduanya termasuk."""
    return (sampai.year - dari.year) * 12 + sampai.month - dari.month + 1


class TagihanMesin(models.AbstractModel):
    """Mesin pembuatan tagihan (spec §4.3) yang dipakai jadwal harian dan wizard Buat Tagihan.

    Semua pembacaan dilakukan sebagai superuser; pemanggil manual (wizard) wajib memeriksa hak lebih dahulu
    dengan `nti_edu.tagihan.akses._nti_edu_cek_hak`.
    """
    _name = 'nti_edu.tagihan.mesin'
    _description = 'Mesin Tagihan Sekolah'

    # --- periode -----------------------------------------------------------------------------

    @api.model
    def _periode_dalam_tahun(self, komponen, tahun_ajaran):
        """Daftar periode tagihan `komponen` pada `tahun_ajaran`, urut tanggal.

        Tiap periode berupa dict: `periode` (tanggal awal periode; `False` untuk dasar sekali), `akhir`, `terbit`,
        `jatuh_tempo`, `semester` (record, boleh kosong), serta `tahun_ajaran`, `awal` (awal rentang keanggotaan
        yang dihitung, tidak sebelum awal tahun ajaran) dan `jumlah_bulan` (banyak bulan kalender periode).
        """
        jenis = komponen.sudo().periode_jenis_id
        ta = tahun_ajaran.sudo()
        if not jenis or not ta:
            return []
        semester_ta = ta.semester_ids.sorted('tanggal_mulai')

        def semester_pada(tanggal):
            return semester_ta.filtered(lambda s: s.tanggal_mulai <= tanggal <= s.tanggal_selesai)[:1]

        def buat(periode, akhir, semester):
            awal = max(periode or ta.tanggal_mulai, ta.tanggal_mulai)
            bulan_pertama = _awal_bulan(awal)
            terbit = _tanggal_dalam_bulan(bulan_pertama, jenis.hari_terbit)
            if jenis.dasar == 'sekali':
                jatuh_tempo = terbit + timedelta(days=jenis.hari_jatuh_tempo)
            else:
                jatuh_tempo = _tanggal_dalam_bulan(bulan_pertama, jenis.hari_jatuh_tempo)
            return {
                'periode': periode, 'akhir': akhir, 'terbit': terbit, 'jatuh_tempo': jatuh_tempo,
                'semester': semester, 'tahun_ajaran': ta, 'awal': awal,
                'jumlah_bulan': _jumlah_bulan(awal, akhir),
            }

        hasil = []
        if jenis.dasar == 'bulan':
            libur = set(jenis.bulan_libur_ids.mapped('nomor'))
            langkah = relativedelta(months=jenis.jumlah_bulan)
            mulai = _awal_bulan(ta.tanggal_mulai)
            while mulai <= ta.tanggal_selesai:
                if mulai.month not in libur:
                    akhir = min(mulai + langkah - timedelta(days=1), ta.tanggal_selesai)
                    hasil.append(buat(mulai, akhir, semester_pada(max(mulai, ta.tanggal_mulai))))
                mulai += langkah
        elif jenis.dasar == 'semester':
            for semester in semester_ta:
                hasil.append(buat(semester.tanggal_mulai, semester.tanggal_selesai, semester))
        elif jenis.dasar == 'tahun_ajaran':
            hasil.append(buat(ta.tanggal_mulai, ta.tanggal_selesai, semester_ta.browse()))
        else:
            hasil.append(buat(False, ta.tanggal_selesai, semester_ta.browse()))
        return hasil

    # --- rencana & penerbitan ----------------------------------------------------------------

    @api.model
    def _rencana(self, company, komponen, info, rombel=None):
        """Siswa unit `company` yang akan ditagih `komponen` untuk periode `info` (dari `_periode_dalam_tahun`).

        Mengembalikan dict `buat` (daftar dict `siswa`, `rombel`, `nominal`, `potongan`, `terbit`, `jatuh_tempo`)
        dan `lewati` (daftar `(siswa, alasan)` untuk siswa yang sebenarnya ditagih tetapi dilewati, mis. sudah
        punya tagihan itu). Siswa yang memang tidak ditagih (tanpa baris skema, mulai periode berikutnya, sebelum
        Tagihan Mulai) tidak dilaporkan. `rombel` (opsional) membatasi ke rombel tersebut.
        """
        hasil = {'buat': [], 'lewati': []}
        company = company.sudo()
        komponen = komponen.sudo()
        jenis = komponen.periode_jenis_id
        ta = info['tahun_ajaran']
        periode = info['periode']
        mulai_tagih = company.nti_edu_tagihan_mulai
        if komponen.jenis != 'biaya' or not jenis:
            return hasil
        if periode and mulai_tagih and periode < mulai_tagih:
            return hasil
        skema = self.env['nti_edu.tagihan.skema'].sudo()._aktif_untuk(company, ta)
        if not skema:
            return hasil

        # Keanggotaan rombel unit ini yang beririsan dengan periode; interval keanggotaan [masuk, keluar).
        Anggota = self.env['nti_edu.rombel.anggota'].sudo()
        anggota = Anggota.search([
            ('company_id', '=', company.id), ('tahun_ajaran_id', '=', ta.id),
            '|', ('tanggal_masuk', '=', False), ('tanggal_masuk', '<=', info['akhir']),
            '|', ('tanggal_keluar', '=', False), ('tanggal_keluar', '>', info['awal']),
            ('siswa_id.nti_edu_is_siswa', '=', True), ('siswa_id.nti_edu_status', '=', 'aktif'),
            ('siswa_id.company_id', '=', company.id),
        ])
        if not anggota:
            return hasil
        semua_siswa = anggota.siswa_id.sorted(lambda s: (s.name or '', s.id))

        sudah = set(self.env['account.move'].sudo().search([
            ('move_type', '=', 'out_invoice'), ('state', '!=', 'cancel'),
            ('nti_edu_komponen_id', '=', komponen.id), ('nti_edu_siswa_id', 'in', semua_siswa.ids),
            ('nti_edu_sumber', '=', False), ('nti_edu_tagihan_asal_id', '=', False),
            ('nti_edu_periode', '=', periode or False),
        ]).nti_edu_siswa_id.ids)
        if not periode and mulai_tagih:
            # Komponen sekali tidak ditagihkan ke siswa yang sudah masuk unit ini sebelum Tagihan Mulai.
            lama = set(Anggota.search([
                ('company_id', '=', company.id), ('siswa_id', 'in', semua_siswa.ids),
                '|', ('tanggal_masuk', '=', False), ('tanggal_masuk', '<', mulai_tagih),
            ]).siswa_id.ids)
        else:
            lama = set()

        # Tanggal masuk paling awal tiap siswa di unit ini dalam periode (kosong = sejak awal periode).
        masuk_siswa = {}
        for a in anggota:
            masuk = a.tanggal_masuk or info['awal']
            masuk_siswa[a.siswa_id.id] = min(masuk, masuk_siswa.get(a.siswa_id.id, masuk))

        mata_uang = company.currency_id
        cara_masuk = komponen.aturan_masuk_id.cara or 'penuh'
        Potongan = self.env['nti_edu.tagihan.potongan'].sudo()
        for siswa in semua_siswa:
            if siswa.id in lama:
                continue
            masuk = masuk_siswa[siswa.id]
            acuan = max(info['awal'], masuk)
            rombel_siswa = siswa._nti_edu_rombel_pada(acuan)
            if not rombel_siswa or rombel_siswa.company_id != company:
                continue
            if rombel and rombel_siswa not in rombel:
                continue
            baris = skema._baris_untuk(komponen, rombel_siswa.tingkat_id, rombel_siswa.jurusan_id)
            if not baris:
                continue
            nominal = baris.nominal
            if periode:
                terbit, jatuh_tempo = info['terbit'], info['jatuh_tempo']
                # Masuk tengah: bulan masuk sesudah bulan pertama periode yang lebih dari satu bulan.
                if info['jumlah_bulan'] > 1 and _awal_bulan(masuk) > _awal_bulan(info['awal']):
                    if cara_masuk == 'berikutnya':
                        continue
                    if cara_masuk == 'prorata':
                        nominal = _bulatkan_satuan(
                            mata_uang, nominal * _jumlah_bulan(masuk, info['akhir']) / info['jumlah_bulan'])
            else:
                # Sekali: terbit pada tanggal terbit awal tahun ajaran, atau tanggal masuk bila lebih akhir.
                terbit = max(info['terbit'], acuan)
                jatuh_tempo = terbit + timedelta(days=jenis.hari_jatuh_tempo)
            if nominal <= 0:
                continue
            if siswa.id in sudah:
                hasil['lewati'].append((siswa, _('sudah ditagih')))
                continue
            hasil['buat'].append({
                'siswa': siswa,
                'rombel': rombel_siswa,
                'nominal': nominal,
                'potongan': Potongan._hitung(siswa, komponen, periode or terbit, nominal),
                'terbit': terbit,
                'jatuh_tempo': jatuh_tempo,
            })
        return hasil

    @api.model
    def _terbitkan(self, company, komponen, info, rombel=None):
        """Terbitkan tagihan sesuai `_rencana`. Tiap siswa diproses dalam savepoint sendiri: galat satu siswa
        dicatat di `lewati` dan tidak menghentikan siswa lain.

        Mengembalikan dict `buat` (recordset `account.move`) dan `lewati` (daftar `(siswa, alasan)`).
        """
        rencana = self._rencana(company, komponen, info, rombel=rombel)
        Move = self.env['account.move']
        tagihan = Move.browse()
        lewati = list(rencana['lewati'])
        for item in rencana['buat']:
            siswa = item['siswa']
            try:
                with self.env.cr.savepoint():
                    tagihan |= Move._nti_edu_terbitkan(
                        siswa, komponen, item['nominal'], item['terbit'], item['jatuh_tempo'],
                        potongan=item['potongan'], periode=info['periode'] or False,
                        tahun_ajaran_id=info['tahun_ajaran'], semester_id=info['semester'],
                        rombel_id=item['rombel'])
            except psycopg2.OperationalError:
                # Konflik transaksi/koneksi: batalkan seluruh proses, jangan dilaporkan sebagai lewati.
                raise
            except Exception as e:  # noqa: BLE001 - galat satu siswa tidak boleh menghentikan yang lain
                galat_pengguna = isinstance(e, UserError)
                alasan = e.args[0] if galat_pengguna and e.args else str(e)
                # Galat pemrograman dicatat lengkap dengan traceback; UserError cukup peringatan singkat.
                _logger.warning(
                    'Tagihan %s periode %s untuk siswa %s (id %s) gagal diterbitkan: %s',
                    komponen.sudo().name, info['periode'] or '-', siswa.sudo().name, siswa.id, alasan,
                    exc_info=not galat_pengguna)
                lewati.append((siswa, alasan))
        return {'buat': tagihan, 'lewati': lewati}

    # --- jadwal ------------------------------------------------------------------------------

    @api.model
    def _cron_buat_tagihan(self, hari_ini=None):
        """Jadwal harian: untuk unit dengan Tagihan Otomatis, terbitkan tagihan setiap komponen biaya pada skema
        aktif tahun ajaran aktif untuk periode yang tanggal terbitnya sudah tiba. Aman dijalankan berulang.

        Di jalur jadwal sungguhan, hasil tiap (unit, komponen, periode) di-commit agar penerbitan awal tahun ajaran
        yang besar tidak hilang seluruhnya bila melewati batas waktu cron; di tes tidak pernah commit."""
        hari_ini = hari_ini or fields.Date.context_today(self)
        ta = self.env['nti_edu.tahun.ajaran'].sudo()._get_aktif()
        if not ta:
            return
        Skema = self.env['nti_edu.tagihan.skema'].sudo()
        units = self.env['res.company'].sudo().search([('nti_edu_tagihan_otomatis', '=', True)])
        pekerjaan = []
        for company in units:
            skema = Skema._aktif_untuk(company, ta)
            daftar_komponen = skema.baris_ids.komponen_id.filtered(lambda k: k.active and k.jenis == 'biaya')
            for komponen in daftar_komponen.sorted(lambda k: (k.sequence, k.id)):
                try:
                    daftar_periode = self._periode_dalam_tahun(komponen, ta)
                except Exception:  # noqa: BLE001
                    _logger.exception('Periode komponen %s tidak dapat dihitung', komponen.name)
                    continue
                pekerjaan += [(company, komponen, info) for info in daftar_periode if info['terbit'] <= hari_ini]

        commit = _boleh_commit()
        Cron = self.env['ir.cron']
        for selesai, (company, komponen, info) in enumerate(pekerjaan, start=1):
            try:
                with self.env.cr.savepoint():
                    hasil = self._terbitkan(company, komponen, info)
            except psycopg2.OperationalError:
                raise
            except Exception:  # noqa: BLE001 - satu komponen rusak tidak menghentikan yang lain
                _logger.exception(
                    'Tagihan otomatis %s %s periode %s gagal', company.name, komponen.name, info['periode'] or '-')
            else:
                if hasil['buat']:
                    _logger.info(
                        'Tagihan otomatis %s %s periode %s: %s terbit, %s dilewati', company.name,
                        komponen.name, info['periode'] or '-', len(hasil['buat']), len(hasil['lewati']))
            if commit:
                Cron._notify_progress(done=selesai, remaining=len(pekerjaan) - selesai)
                self.env.cr.commit()

    # --- denda -------------------------------------------------------------------------------

    @api.model
    def _cron_denda(self, hari_ini=None):
        """Jadwal harian denda keterlambatan (spec §4.5). Aman dijalankan berulang dan mengejar hari yang terlewat.

        Untuk tagihan biaya terbit yang komponennya punya aturan denda aktif (tunggakan awal hanya bila pengaturan
        unit `nti_edu_denda_saldo_awal`), tiap baris piutang (cicilan) yang masih bersisa dan jatuh temponya tidak
        sebelum Tagihan Mulai unit dinilai sendiri: batas ke-n = jatuh tempo + tenggang + (n − 1) bulan; denda ke-n
        terbit bila batasnya sudah lewat (`sekali` hanya n = 1) dan belum pernah ada (denda yang dihapus tidak
        diterbitkan lagi). Di jalur jadwal sungguhan hasil tiap tagihan asal di-commit; di tes tidak pernah commit.
        """
        hari_ini = hari_ini or fields.Date.context_today(self)
        Move = self.env['account.move'].sudo()
        daftar_komponen = self.env['nti_edu.tagihan.komponen'].sudo().with_context(active_test=False).search([
            ('jenis', '=', 'biaya'), ('aturan_denda_id', '!=', False)]).filtered('aturan_denda_id.active')
        if not daftar_komponen:
            return
        kandidat = Move.search([
            ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('nti_edu_is_tagihan', '=', True),
            ('nti_edu_komponen_id', 'in', daftar_komponen.ids), ('nti_edu_tagihan_asal_id', '=', False),
            ('amount_residual', '>', 0),
        ], order='company_id, id')
        kandidat = kandidat.filtered(lambda m: not m.nti_edu_saldo_awal or m.company_id.nti_edu_denda_saldo_awal)

        commit = _boleh_commit()
        Cron = self.env['ir.cron']
        for selesai, asal in enumerate(kandidat, start=1):
            try:
                with self.env.cr.savepoint():
                    self._denda_tagihan(asal, hari_ini)
            except psycopg2.OperationalError:
                raise
            except Exception as e:  # noqa: BLE001 - satu tagihan rusak tidak menghentikan yang lain
                galat_pengguna = isinstance(e, UserError)
                _logger.warning(
                    'Denda tagihan %s (id %s) gagal diterbitkan: %s', asal.name, asal.id,
                    e.args[0] if galat_pengguna and e.args else e, exc_info=not galat_pengguna)
            if commit:
                Cron._notify_progress(done=selesai, remaining=len(kandidat) - selesai)
                self.env.cr.commit()

    @api.model
    def _denda_tagihan(self, asal, hari_ini):
        """Terbitkan semua denda `asal` (sudo) yang sudah jatuh pada `hari_ini` dan belum ada; urut jatuh tempo
        cicilan lalu bulan ke-n, masing-masing dipangkas ke sisa batas maksimum aturan. Mengembalikan denda baru."""
        aturan = asal.nti_edu_komponen_id.aturan_denda_id
        company = asal.company_id
        mata_uang = asal.currency_id
        Move = self.env['account.move'].sudo()
        hasil = Move.browse()
        # Tunggakan awal memang berjatuh tempo sebelum Tagihan Mulai; ia hanya dibatasi pengaturan denda saldo awal.
        mulai = not asal.nti_edu_saldo_awal and company.nti_edu_tagihan_mulai
        piutang = asal.line_ids.filtered(
            lambda b: b.account_id.account_type == 'asset_receivable' and b.date_maturity
            and mata_uang.compare_amounts(b.amount_residual_currency, 0.0) > 0
            and (not mulai or b.date_maturity >= mulai))
        if not piutang:
            return hasil
        # Semua denda yang pernah ada, termasuk yang dibatalkan (dihapus), tidak diterbitkan ulang.
        lama = Move.search([('move_type', '=', 'out_invoice'), ('nti_edu_tagihan_asal_id', '=', asal.id)])
        sudah = {(d.nti_edu_denda_jatuh_tempo, d.nti_edu_denda_bulan_ke) for d in lama}
        total = sum(lama.filtered(lambda d: d.state != 'cancel').mapped('amount_total'))
        kali = 1 if aturan.berulang == 'sekali' else None
        for baris in piutang.sorted(lambda b: (b.date_maturity, b.id)):
            jatuh_tempo = baris.date_maturity
            batas_awal = jatuh_tempo + timedelta(days=aturan.tenggang_hari)
            n = 1
            while (kali is None or n <= kali) and batas_awal + relativedelta(months=n - 1) < hari_ini:
                if (jatuh_tempo, n) not in sudah:
                    if aturan.tipe == 'persen':
                        jumlah = _bulatkan_satuan(mata_uang, baris.amount_residual_currency * aturan.nilai / 100.0)
                    else:
                        jumlah = mata_uang.round(aturan.nilai)
                    if aturan.maks:
                        sisa_maks = mata_uang.round(aturan.maks - total)
                        if mata_uang.compare_amounts(sisa_maks, 0.0) <= 0:
                            return hasil
                        jumlah = min(jumlah, sisa_maks)
                    if mata_uang.compare_amounts(jumlah, 0.0) > 0:
                        denda = Move._nti_edu_terbitkan(
                            asal.nti_edu_siswa_id, aturan.komponen_denda_id, jumlah, hari_ini, hari_ini,
                            company=company, tagihan_asal_id=asal, denda_jatuh_tempo=jatuh_tempo, denda_bulan_ke=n)
                        hasil |= denda
                        total += denda.amount_total
                n += 1
        return hasil

    # --- pembayaran --------------------------------------------------------------------------

    @api.model
    def _bayar(self, tagihan, jumlah, rekening, tanggal, memo, siswa_kelebihan=None):
        """Catat pembayaran `jumlah` atas `tagihan` (spec §4.6) ke jurnal `rekening`, lalu rekonsiliasi.

        Semua tagihan harus tagihan sekolah terbit dari satu unit; pemanggil harus Bendahara unit itu (atau
        superuser). Alokasi urut jatuh tempo (lalu id), hanya sampai sisa tiap tagihan. Per siswa dibuat satu
        payment lewat wizard pembayaran standar Odoo dan direkonsiliasi dengan tagihan siswa itu. Kelebihan
        (`jumlah` − total sisa) ditambahkan ke payment `siswa_kelebihan` (bawaan: siswa pertama menurut nama)
        sehingga menjadi kredit tak terpakai siswa itu (saldo kredit). Penulisan sebagai superuser; uid pemanggil
        tetap tercatat. Mengembalikan payment yang dibuat (env pemanggil).
        """
        semua = tagihan.sudo()
        if not semua:
            raise UserError(_('Pilih minimal satu tagihan yang dibayar.'))
        company = semua.company_id
        if len(company) != 1:
            raise UserError(_('Tagihan yang dibayar sekaligus harus dari satu unit.'))
        self.env['nti_edu.tagihan.akses']._nti_edu_cek_hak(GRUP_BENDAHARA, company)
        if semua.filtered(lambda m: m.move_type != 'out_invoice' or not m.nti_edu_is_tagihan):
            raise UserError(_('Dokumen yang dipilih bukan tagihan sekolah.'))
        belum = semua.filtered(lambda m: m.state != 'posted')
        if belum:
            raise UserError(_('Tagihan %s tidak berstatus terbit sehingga tidak dapat dibayar.',
                              ', '.join(belum.mapped('name'))))
        mata_uang = company.currency_id
        if semua.currency_id != mata_uang:
            raise UserError(_('Tagihan dengan mata uang selain mata uang unit tidak dapat dibayar di sini.'))
        if mata_uang.compare_amounts(jumlah or 0.0, 0.0) <= 0:
            raise UserError(_('Nominal pembayaran harus lebih dari nol.'))
        rekening = rekening.sudo()
        if not rekening:
            raise UserError(_('Pilih rekening atau kas penerima pembayaran.'))
        if rekening not in rekening._untuk_unit(company):
            raise UserError(_('Rekening "%(rekening)s" tidak berlaku untuk unit %(unit)s.',
                              rekening=rekening.name, unit=company.name))
        daftar_siswa = semua.nti_edu_siswa_id.sorted(lambda s: (s.name or '', s.id))
        if siswa_kelebihan:
            siswa_kelebihan = siswa_kelebihan.sudo()
            if siswa_kelebihan not in daftar_siswa:
                raise UserError(_('Siswa penerima kelebihan bukan siswa pada tagihan yang dibayar.'))
        else:
            siswa_kelebihan = daftar_siswa[:1]

        # Alokasi ke sisa tagihan, jatuh tempo paling lama lebih dahulu.
        sisa_uang = mata_uang.round(jumlah)
        alokasi = {}
        baris_siswa = {}
        for item in semua.sorted(lambda m: (m.invoice_date_due or m.invoice_date, m.id)):
            if mata_uang.compare_amounts(sisa_uang, 0.0) <= 0:
                break
            if mata_uang.compare_amounts(item.amount_residual, 0.0) <= 0:
                continue
            bagian = min(sisa_uang, item.amount_residual)
            siswa_id = item.nti_edu_siswa_id.id
            alokasi[siswa_id] = alokasi.get(siswa_id, 0.0) + bagian
            piutang = item.line_ids.filtered(
                lambda b: b.account_id.account_type == 'asset_receivable' and not b.reconciled)
            baris_siswa[siswa_id] = baris_siswa.get(siswa_id, piutang.browse()) | piutang
            sisa_uang = mata_uang.round(sisa_uang - bagian)
        kelebihan = max(sisa_uang, 0.0)

        payments = self.env['account.payment'].sudo()
        for siswa in daftar_siswa:
            nominal = alokasi.get(siswa.id, 0.0)
            if siswa == siswa_kelebihan:
                nominal += kelebihan
            nominal = mata_uang.round(nominal)
            if mata_uang.compare_amounts(nominal, 0.0) <= 0:
                continue
            baris = baris_siswa.get(siswa.id)
            if baris:
                payments |= self._bayar_baris(siswa, baris, nominal, rekening, tanggal, memo)
            else:
                payments |= self._bayar_kredit(siswa, company, nominal, rekening, tanggal, memo)
        # Odoo 18 tidak membuat entri jurnal untuk payment tanpa akun penampung: tagihan tidak berkurang dan
        # kelebihan tidak menjadi kredit. Batalkan semuanya (UserError → transaksi dibatalkan) daripada diam-diam.
        tanpa_entri = payments.filtered(lambda p: not p.move_id)
        if tanpa_entri:
            raise UserError(_(
                'Pembayaran tidak dapat dicatat: metode pembayaran masuk jurnal "%s" belum punya akun penampung '
                '(Outstanding Receipts). Hubungi bagian akuntansi untuk mengisinya.',
                rekening.journal_id.name))
        payments.write({'nti_edu_dari_tagihan': True})
        return payments.with_env(self.env)

    @api.model
    def _bayar_baris(self, siswa, baris, nominal, rekening, tanggal, memo):
        """Satu payment `nominal` untuk baris piutang `baris` milik `siswa` lewat `account.payment.register`;
        nominal di atas total sisa baris tetap terbuka sebagai kredit siswa."""
        company = baris.company_id
        Register = self.env['account.payment.register'].sudo().with_company(company).with_context(
            active_model='account.move.line', active_ids=baris.ids)
        nilai = {
            'amount': nominal,
            'journal_id': rekening.journal_id.id,
            'payment_method_line_id': rekening._nti_edu_metode_masuk().id,
            'payment_date': tanggal,
            'group_payment': True,
            'payment_difference_handling': 'open',
        }
        if memo:
            nilai['communication'] = memo
        wizard = Register.create(nilai)
        if not wizard.can_edit_wizard:
            # Tanpa mode sunting, wizard Odoo membayar penuh seluruh baris dan mengabaikan nominal.
            raise UserError(_(
                'Tagihan %s tidak dapat dibayar dalam satu pembayaran (akun piutang atau mata uang berbeda).',
                siswa.name))
        with _bayar_tagihan():
            return wizard._create_payments()

    @api.model
    def _bayar_sebagai_kredit(self, siswa, company, jumlah, rekening, tanggal, memo):
        """Catat pembayaran `jumlah` untuk `siswa` di unit `company` tanpa tagihan: seluruhnya menjadi saldo kredit
        siswa. Penjaga sama dengan `_bayar` (hak Bendahara unit, siswa unit itu, nominal > 0, rekening berlaku untuk
        unit, payment harus punya entri jurnal). Mengembalikan payment (env pemanggil)."""
        siswa = siswa.sudo()
        company = company.sudo()
        if len(siswa) != 1 or len(company) != 1:
            raise UserError(_('Pilih satu siswa dan satu unit penerima kredit.'))
        self.env['nti_edu.tagihan.akses']._nti_edu_cek_hak(GRUP_BENDAHARA, company)
        if not siswa.nti_edu_is_siswa:
            raise UserError(_('"%s" bukan siswa sehingga tidak dapat menerima kredit.', siswa.display_name))
        mata_uang = company.currency_id
        if mata_uang.compare_amounts(jumlah or 0.0, 0.0) <= 0:
            raise UserError(_('Nominal pembayaran harus lebih dari nol.'))
        rekening = rekening.sudo()
        if not rekening:
            raise UserError(_('Pilih rekening atau kas penerima pembayaran.'))
        if rekening not in rekening._untuk_unit(company):
            raise UserError(_('Rekening "%(rekening)s" tidak berlaku untuk unit %(unit)s.',
                              rekening=rekening.name, unit=company.name))
        payment = self._bayar_kredit(siswa, company, mata_uang.round(jumlah), rekening, tanggal, memo)
        if not payment.move_id:
            raise UserError(_(
                'Pembayaran tidak dapat dicatat: metode pembayaran masuk jurnal "%s" belum punya akun penampung '
                '(Outstanding Receipts). Hubungi bagian akuntansi untuk mengisinya.',
                rekening.journal_id.name))
        return payment.with_env(self.env)

    @api.model
    def _bayar_kredit(self, siswa, company, nominal, rekening, tanggal, memo):
        """Payment `nominal` untuk `siswa` tanpa tagihan terbuka: seluruhnya menjadi kredit siswa."""
        payment = self.env['account.payment'].sudo().with_company(company).create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': siswa.id,
            'company_id': company.id,
            'journal_id': rekening.journal_id.id,
            'payment_method_line_id': rekening._nti_edu_metode_masuk().id,
            'amount': nominal,
            'date': tanggal,
            'memo': memo or False,
            'nti_edu_dari_tagihan': True,
        })
        payment.action_post()
        return payment
