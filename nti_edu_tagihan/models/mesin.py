# -*- coding: utf-8 -*-
import calendar
import logging
from datetime import timedelta

import psycopg2
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


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
                        nominal = mata_uang.round(
                            nominal * _jumlah_bulan(masuk, info['akhir']) / info['jumlah_bulan'])
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
                alasan = e.args[0] if isinstance(e, UserError) and e.args else str(e)
                _logger.warning(
                    'Tagihan %s periode %s untuk siswa %s (id %s) gagal diterbitkan: %s',
                    komponen.sudo().name, info['periode'] or '-', siswa.sudo().name, siswa.id, alasan)
                lewati.append((siswa, alasan))
        return {'buat': tagihan, 'lewati': lewati}

    # --- jadwal ------------------------------------------------------------------------------

    @api.model
    def _cron_buat_tagihan(self, hari_ini=None):
        """Jadwal harian: untuk unit dengan Tagihan Otomatis, terbitkan tagihan setiap komponen biaya pada skema
        aktif tahun ajaran aktif untuk periode yang tanggal terbitnya sudah tiba. Aman dijalankan berulang."""
        hari_ini = hari_ini or fields.Date.context_today(self)
        ta = self.env['nti_edu.tahun.ajaran'].sudo()._get_aktif()
        if not ta:
            return
        Skema = self.env['nti_edu.tagihan.skema'].sudo()
        units = self.env['res.company'].sudo().search([('nti_edu_tagihan_otomatis', '=', True)])
        for company in units:
            skema = Skema._aktif_untuk(company, ta)
            daftar_komponen = skema.baris_ids.komponen_id.filtered(lambda k: k.active and k.jenis == 'biaya')
            for komponen in daftar_komponen.sorted(lambda k: (k.sequence, k.id)):
                try:
                    daftar_periode = self._periode_dalam_tahun(komponen, ta)
                except Exception:  # noqa: BLE001
                    _logger.exception('Periode komponen %s tidak dapat dihitung', komponen.name)
                    continue
                for info in daftar_periode:
                    if info['terbit'] > hari_ini:
                        continue
                    try:
                        with self.env.cr.savepoint():
                            hasil = self._terbitkan(company, komponen, info)
                    except psycopg2.OperationalError:
                        raise
                    except Exception:  # noqa: BLE001 - satu komponen rusak tidak menghentikan yang lain
                        _logger.exception(
                            'Tagihan otomatis %s %s periode %s gagal', company.name, komponen.name,
                            info['periode'] or '-')
                        continue
                    if hasil['buat']:
                        _logger.info(
                            'Tagihan otomatis %s %s periode %s: %s terbit, %s dilewati', company.name,
                            komponen.name, info['periode'] or '-', len(hasil['buat']), len(hasil['lewati']))
