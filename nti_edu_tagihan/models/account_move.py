# -*- coding: utf-8 -*-
from datetime import timedelta

from dateutil.relativedelta import relativedelta
from markupsafe import Markup
from psycopg2 import errors

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_amount, format_date, mute_logger

from .mesin import _bulatkan_satuan

GRUP_BENDAHARA = 'nti_edu_tagihan.group_tagihan_bendahara'
GRUP_ADMIN = 'nti_edu_tagihan.group_tagihan_admin'


def _format_nominal(nilai):
    """Nominal untuk nama termin cicilan, tidak bergantung bahasa: 250.000 atau 250.000,50."""
    teks = ('{:,.0f}' if float(nilai).is_integer() else '{:,.2f}').format(nilai)
    return teks.translate(str.maketrans(',.', '.,'))

# Nilai `**sekolah` yang boleh diberikan ke `_nti_edu_terbitkan`, dipetakan ke field `nti_edu_<nama>`.
FIELD_SEKOLAH = (
    'periode', 'tahun_ajaran_id', 'semester_id', 'rombel_id', 'tagihan_asal_id', 'denda_jatuh_tempo',
    'denda_bulan_ke', 'saldo_awal', 'sumber',
)

# Field partner tagihan yang boleh beda unit dengan tagihannya: siswa yang pindah unit tetap ditagih denda di unit
# tagihan asal (lihat `_nti_edu_terbitkan(company=...)`).
FIELD_PARTNER_SISWA = ('partner_id', 'commercial_partner_id', 'partner_shipping_id')

# Indeks unik parsial pencegah tagihan ganda (spec §4.3); tagihan yang dibatalkan tidak dihitung.
INDEKS_UNIK = {
    'nti_edu_tagihan_unik_periode': (
        '(nti_edu_siswa_id, nti_edu_komponen_id, nti_edu_periode)',
        "move_type = 'out_invoice' AND nti_edu_komponen_id IS NOT NULL AND nti_edu_sumber IS NULL "
        "AND nti_edu_tagihan_asal_id IS NULL AND nti_edu_periode IS NOT NULL"),
    'nti_edu_tagihan_unik_sekali': (
        '(nti_edu_siswa_id, nti_edu_komponen_id)',
        "move_type = 'out_invoice' AND nti_edu_komponen_id IS NOT NULL AND nti_edu_sumber IS NULL "
        "AND nti_edu_tagihan_asal_id IS NULL AND nti_edu_periode IS NULL"),
    'nti_edu_tagihan_unik_sumber': (
        '(nti_edu_sumber)',
        'nti_edu_sumber IS NOT NULL'),
    'nti_edu_tagihan_unik_denda': (
        '(nti_edu_tagihan_asal_id, nti_edu_denda_jatuh_tempo, nti_edu_denda_bulan_ke)',
        'nti_edu_tagihan_asal_id IS NOT NULL'),
    'nti_edu_tagihan_unik_potongan': (
        '(nti_edu_potongan_id, reversed_entry_id)',
        'nti_edu_potongan_id IS NOT NULL'),
}


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Field sekolah hanya diisi metode modul; copy=False agar duplikasi invoice oleh akuntan bukan tagihan sekolah.
    nti_edu_siswa_id = fields.Many2one(
        'res.partner', string='Siswa', readonly=True, copy=False, index=True, ondelete='restrict')
    nti_edu_komponen_id = fields.Many2one(
        'nti_edu.tagihan.komponen', string='Komponen Biaya', readonly=True, copy=False, index=True,
        ondelete='restrict')
    nti_edu_periode = fields.Date(
        string='Periode', readonly=True, copy=False,
        help='Tanggal awal periode tagihan; kosong untuk komponen sekali.')
    nti_edu_tahun_ajaran_id = fields.Many2one(
        'nti_edu.tahun.ajaran', string='Tahun Ajaran', readonly=True, copy=False, ondelete='restrict')
    nti_edu_semester_id = fields.Many2one(
        'nti_edu.semester', string='Semester', readonly=True, copy=False, ondelete='restrict')
    nti_edu_rombel_id = fields.Many2one(
        'nti_edu.rombel', string='Rombel', readonly=True, copy=False, ondelete='restrict',
        help='Rombel siswa saat tagihan terbit.')
    nti_edu_tagihan_asal_id = fields.Many2one(
        'account.move', string='Tagihan Asal', readonly=True, copy=False, index=True, ondelete='restrict',
        help='Untuk denda: tagihan yang terlambat dibayar.')
    nti_edu_denda_jatuh_tempo = fields.Date(string='Jatuh Tempo yang Didenda', readonly=True, copy=False)
    nti_edu_denda_bulan_ke = fields.Integer(string='Denda Bulan Ke', readonly=True, copy=False)
    nti_edu_saldo_awal = fields.Boolean(string='Tunggakan Awal', readonly=True, copy=False)
    nti_edu_sumber = fields.Char(
        string='Sumber', readonly=True, copy=False, index=True,
        help='Dokumen asal tagihan dari modul lain (model,id).')
    nti_edu_potongan_id = fields.Many2one(
        'nti_edu.tagihan.potongan', string='Potongan', readonly=True, copy=False, index=True,
        ondelete='restrict', help='Potongan siswa yang diterapkan lewat nota kredit ini.')
    nti_edu_is_tagihan = fields.Boolean(
        string='Tagihan Sekolah', compute='_compute_nti_edu_is_tagihan', store=True, index=True)
    nti_edu_komponen_jenis = fields.Selection(related='nti_edu_komponen_id.jenis', string='Jenis Komponen')
    nti_edu_boleh_hapus_denda = fields.Boolean(
        string='Boleh Hapus Denda', compute='_compute_nti_edu_boleh_hapus_denda',
        help='Hanya untuk tampilan tombol Hapus Denda; penjaga sebenarnya ada di _nti_edu_hapus_denda.')
    nti_edu_lunas = fields.Boolean(string='Lunas', compute='_compute_nti_edu_lunas')
    nti_edu_ada_kredit = fields.Boolean(
        string='Ada Kredit Siswa', compute='_compute_nti_edu_ada_kredit',
        help='Siswa punya pembayaran atau nota kredit yang belum terpakai yang bisa diterapkan ke tagihan ini.')
    nti_edu_boleh_cicil = fields.Boolean(
        string='Boleh Dicicil', compute='_compute_nti_edu_boleh_cicil',
        help='Tagihan terbit yang belum dibayar sama sekali dan komponennya punya aturan cicilan.')
    nti_edu_menunggu_verifikasi = fields.Boolean(
        string='Menunggu Verifikasi', compute='_compute_nti_edu_menunggu_verifikasi',
        search='_search_nti_edu_menunggu_verifikasi',
        help='Tagihan ini ada di konfirmasi transfer yang belum diverifikasi Bendahara; tetap bisa dibayar tunai.')

    def init(self):
        super().init()
        for nama, (kolom, syarat) in INDEKS_UNIK.items():
            self.env.cr.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {nama} ON account_move {kolom} "
                f"WHERE state != 'cancel' AND {syarat}")

    def _check_company(self, fnames=None):
        """Hanya saat `_nti_edu_terbitkan` menerbitkan tagihan di unit selain unit siswa saat ini (konteks
        `nti_edu_partner_lintas_unit`): partner siswa tagihan sekolah tidak diperiksa unitnya; field lain tetap."""
        if not self.env.context.get('nti_edu_partner_lintas_unit'):
            return super()._check_company(fnames)
        lintas = self.filtered(lambda m: m.nti_edu_is_tagihan and m.partner_id == m.nti_edu_siswa_id)
        if self - lintas:
            super(AccountMove, self - lintas)._check_company(fnames)
        if lintas:
            if fnames is None or {'company_id', 'company_ids'} & set(fnames):
                fnames = list(self._fields)
            sisa = [f for f in fnames if f not in FIELD_PARTNER_SISWA + ('company_id', 'company_ids')]
            if sisa:
                super(AccountMove, lintas)._check_company(sisa)

    @api.depends('nti_edu_komponen_id')
    def _compute_nti_edu_is_tagihan(self):
        for move in self:
            move.nti_edu_is_tagihan = bool(move.nti_edu_komponen_id)

    @api.depends('state', 'amount_residual', 'currency_id')
    def _compute_nti_edu_lunas(self):
        for move in self:
            move.nti_edu_lunas = move.state == 'posted' and move.currency_id.is_zero(move.amount_residual)

    def _nti_edu_tagihan_menunggu(self):
        """Tagihan yang termuat di konfirmasi transfer berstatus menunggu (dibaca sebagai superuser: pembaca
        tagihan belum tentu berhak membaca konfirmasinya, mis. portal)."""
        konfirmasi = self.env['nti_edu.tagihan.konfirmasi'].sudo().search([('state', '=', 'menunggu')])
        return konfirmasi.tagihan_ids

    def _compute_nti_edu_menunggu_verifikasi(self):
        menunggu = set()
        if self._origin.ids:
            menunggu = set(self.env['nti_edu.tagihan.konfirmasi'].sudo().search([
                ('state', '=', 'menunggu'), ('tagihan_ids', 'in', self._origin.ids)]).tagihan_ids.ids)
        for move in self:
            move.nti_edu_menunggu_verifikasi = move._origin.id in menunggu

    def _search_nti_edu_menunggu_verifikasi(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise UserError(_('Operasi pencarian tidak didukung untuk Menunggu Verifikasi.'))
        ada = (operator == '=') == value
        return [('id', 'in' if ada else 'not in', self._nti_edu_tagihan_menunggu().ids)]

    # --- penerbitan --------------------------------------------------------------------------

    @api.model
    def _nti_edu_terbitkan(self, siswa, komponen, nominal, tanggal, jatuh_tempo, potongan=(), keterangan=None,
                           company=None, **sekolah):
        """Terbitkan satu tagihan (invoice posted) untuk `siswa` atas `komponen` sebesar `nominal`.

        `potongan`: daftar `(jenis_potongan, jumlah)` yang menjadi baris minus "Potongan <jenis>".
        `sekolah`: nilai field `nti_edu_<nama>` (lihat FIELD_SEKOLAH); record boleh diberikan langsung.
        Hak pemanggil diperiksa oleh pemanggil (`nti_edu.tagihan.akses`); penulisan dilakukan sebagai superuser
        dengan uid pemanggil tetap tercatat. Tagihan ganda → `UserError`.
        `company`: unit tagihan bila bukan unit siswa saat ini (mis. denda mengikuti unit tagihan asal).
        """
        siswa.ensure_one()
        if not siswa.sudo().nti_edu_is_siswa:
            raise UserError(_('"%s" bukan siswa sehingga tidak dapat ditagih.', siswa.sudo().display_name))
        company = company.sudo() if company else siswa.sudo().company_id
        if not company:
            raise UserError(_('Siswa "%s" belum memiliki unit sekolah.', siswa.display_name))
        if nominal < 0:
            raise UserError(_('Nominal tagihan tidak boleh negatif.'))
        tidak_dikenal = set(sekolah) - set(FIELD_SEKOLAH)
        if tidak_dikenal:
            raise ValueError('Field sekolah tidak dikenal: %s' % ', '.join(sorted(tidak_dikenal)))

        komponen = komponen.sudo()
        nilai_baris = {
            'product_id': komponen.product_id.id,
            'quantity': 1,
            'tax_ids': [Command.clear()],
        }
        if komponen.akun_pendapatan_id:
            nilai_baris['account_id'] = komponen.akun_pendapatan_id.id
        baris = [Command.create(dict(nilai_baris, name=keterangan or komponen.name, price_unit=nominal))]
        for jenis, jumlah in potongan:
            baris.append(Command.create(dict(
                nilai_baris, name=_('Potongan %s', jenis.name), price_unit=-jumlah,
                nti_edu_potongan_jenis_id=jenis.id)))

        vals = {
            'move_type': 'out_invoice',
            'company_id': company.id,
            'journal_id': company._nti_edu_jurnal_tagihan().id,
            'partner_id': siswa.id,
            'invoice_date': tanggal,
            'invoice_date_due': jatuh_tempo,
            'invoice_payment_term_id': False,
            'invoice_line_ids': baris,
            'nti_edu_siswa_id': siswa.id,
            'nti_edu_komponen_id': komponen.id,
        }
        for nama, nilai in sekolah.items():
            vals['nti_edu_' + nama] = nilai.id if isinstance(nilai, models.BaseModel) else nilai

        Move = self.sudo().with_company(company)
        if company != siswa.sudo().company_id:
            Move = Move.with_context(nti_edu_partner_lintas_unit=True)
        try:
            with self.env.cr.savepoint():
                # Kolom indeks unik tagihan semuanya ditulis saat INSERT; log SQL hanya dibisukan di sini.
                with mute_logger('odoo.sql_db'):
                    tagihan = Move.create(vals)
                tagihan.action_post()
        except errors.UniqueViolation as e:
            pesan = self._nti_edu_pesan_ganda(e.diag.constraint_name, siswa, komponen)
            if not pesan:
                raise
            raise UserError(pesan) from None
        return tagihan.with_env(self.env)

    @api.model
    def _nti_edu_pesan_ganda(self, indeks, siswa, komponen):
        """Pesan ramah untuk pelanggaran indeks unik tagihan; `False` bila `indeks` bukan indeks tagihan
        (galat lain diteruskan apa adanya sehingga pemanggil tidak salah melaporkan "sudah ditagih")."""
        if indeks not in INDEKS_UNIK:
            return False
        if indeks == 'nti_edu_tagihan_unik_sumber':
            return _('Tagihan ini sudah ada untuk dokumen sumber yang sama.')
        if indeks == 'nti_edu_tagihan_unik_denda':
            return _('Tagihan ini sudah ada: denda untuk keterlambatan yang sama sudah diterbitkan.')
        if indeks == 'nti_edu_tagihan_unik_potongan':
            return _('Tagihan ini sudah ada: potongan ini sudah diterapkan pada tagihan tersebut.')
        return _('Tagihan ini sudah ada: %(komponen)s untuk %(siswa)s pada periode yang sama.',
                 komponen=komponen.name, siswa=siswa.display_name)

    # --- koreksi ----------------------------------------------------------------------------

    def _nti_edu_batalkan(self, alasan):
        """Batalkan tagihan yang belum dibayar sama sekali; alasan dicatat di chatter atas nama pemanggil.

        Hanya Bendahara unit tagihan (atau Admin Keuangan). Tagihan yang sudah dibayar sebagian/lunas dikoreksi
        dengan nota kredit standar (spec §4.3).
        """
        if not (alasan or '').strip():
            raise UserError(_('Alasan pembatalan wajib diisi.'))
        semua = self.sudo()
        # Hak lebih dahulu, agar pemanggil tanpa hak tidak mendapat informasi apa pun tentang dokumennya.
        self.env['nti_edu.tagihan.akses']._nti_edu_cek_hak(GRUP_BENDAHARA, semua.company_id)
        bukan = semua.filtered(lambda m: m.move_type != 'out_invoice' or not m.nti_edu_is_tagihan)
        if bukan:
            raise UserError(_('%s bukan tagihan sekolah.', self._nti_edu_nama_terlihat(bukan)))
        denda = semua.filtered(lambda m: m.nti_edu_komponen_id.jenis == 'denda')
        if denda:
            # Denda hanya dibatalkan lewat Hapus Denda (alasan master, hak menurut pengaturan unit).
            raise UserError(_('%s adalah tagihan denda; gunakan Hapus Denda.', self._nti_edu_nama_terlihat(denda)))
        for tagihan in semua:
            if tagihan.state != 'posted':
                raise UserError(_('Tagihan %s tidak berstatus terbit sehingga tidak dapat dibatalkan.',
                                  tagihan.name))
            if tagihan.currency_id.compare_amounts(tagihan.amount_residual, tagihan.amount_total) != 0:
                raise UserError(_(
                    'Tagihan %s sudah dibayar atau dikoreksi sebagian sehingga tidak dapat dibatalkan; gunakan '
                    'nota kredit.', tagihan.name))
        penulis = self.env.user.partner_id.id
        for tagihan in semua:
            tagihan.button_draft()
            tagihan.button_cancel()
            tagihan.message_post(body=_('Tagihan dibatalkan. Alasan: %s', alasan), author_id=penulis)
        return True

    @api.depends('state', 'move_type', 'amount_residual', 'amount_total', 'nti_edu_komponen_id', 'company_id',
                 'company_id.nti_edu_denda_hapus_perlu_admin')
    @api.depends_context('uid')
    def _compute_nti_edu_boleh_hapus_denda(self):
        user = self.env.user
        su = self.env.su
        unit_user = user.sudo().company_ids
        admin = user.has_group(GRUP_ADMIN)
        bendahara = user.has_group(GRUP_BENDAHARA)
        for move in self:
            company = move.sudo().company_id
            if su:
                berhak = True
            elif company.nti_edu_denda_hapus_perlu_admin:
                berhak = admin and company in unit_user
            else:
                berhak = bendahara and company in unit_user
            move.nti_edu_boleh_hapus_denda = bool(
                berhak and move.move_type == 'out_invoice' and move.state == 'posted'
                and move.nti_edu_komponen_id.sudo().jenis == 'denda'
                and move.currency_id.compare_amounts(move.amount_residual, move.amount_total) == 0)

    def _nti_edu_hapus_denda(self, alasan, catatan=False):
        """Hapus (batalkan) tagihan denda yang belum dibayar sama sekali dengan `alasan` dari master alasan
        penghapusan denda (spec §4.5); `catatan` wajib bila alasan mewajibkannya. Dicatat di chatter atas nama
        pemanggil.

        Hak: Admin Keuangan bila unit denda mengaktifkan `nti_edu_denda_hapus_perlu_admin`, selain itu Bendahara
        unit itu. Penulisan sebagai superuser.
        """
        semua = self.sudo()
        if not semua:
            raise UserError(_('Pilih minimal satu tagihan denda yang dihapus.'))
        # Hak lebih dahulu, agar pemanggil tanpa hak tidak mendapat informasi apa pun tentang dokumennya.
        Akses = self.env['nti_edu.tagihan.akses']
        perlu_admin = semua.company_id.filtered('nti_edu_denda_hapus_perlu_admin')
        if perlu_admin:
            Akses._nti_edu_cek_hak(GRUP_ADMIN, perlu_admin)
        if semua.company_id - perlu_admin:
            Akses._nti_edu_cek_hak(GRUP_BENDAHARA, semua.company_id - perlu_admin)
        alasan = alasan.sudo()
        catatan = (catatan or '').strip()
        if not alasan:
            raise UserError(_('Alasan penghapusan denda wajib dipilih.'))
        if alasan.perlu_catatan and not catatan:
            raise UserError(_('Alasan "%s" mewajibkan catatan.', alasan.name))
        bukan = semua.filtered(lambda m: m.move_type != 'out_invoice' or not m.nti_edu_is_tagihan
                               or m.nti_edu_komponen_id.jenis != 'denda')
        if bukan:
            raise UserError(_('%s bukan tagihan denda.', self._nti_edu_nama_terlihat(bukan)))
        for denda in semua:
            if not alasan.filtered_domain(alasan._check_company_domain(denda.company_id)):
                raise UserError(_('Alasan "%(alasan)s" tidak berlaku untuk unit %(unit)s.',
                                  alasan=alasan.name, unit=denda.company_id.name))
            if denda.state != 'posted':
                raise UserError(_('Denda %s tidak berstatus terbit sehingga tidak dapat dihapus.', denda.name))
            if denda.currency_id.compare_amounts(denda.amount_residual, denda.amount_total) != 0:
                raise UserError(_('Denda %s sudah dibayar atau dikoreksi sebagian sehingga tidak dapat dihapus.',
                                  denda.name))
        penulis = self.env.user.partner_id.id
        teks = _('Denda dihapus: %(alasan)s%(catatan)s',
                 alasan=alasan.name, catatan=(' — %s' % catatan) if catatan else '')
        for denda in semua:
            denda.button_draft()
            denda.button_cancel()
            denda.message_post(body=teks, author_id=penulis)
        return True

    @api.model
    def _nti_edu_nama_terlihat(self, moves):
        """Nama `moves` untuk pesan galat: hanya dokumen yang boleh dibaca pemanggil yang disebut namanya,
        sisanya cukup dihitung."""
        terlihat = self.browse(moves.ids)._filtered_access('read')
        nama = terlihat.mapped('display_name')
        lain = len(moves) - len(terlihat)
        if lain:
            nama.append(_('%s dokumen lain', lain))
        return ', '.join(nama)

    def _nti_edu_terbuka(self):
        """True bila ini tagihan sekolah terbit yang masih bersisa."""
        self.ensure_one()
        return self.move_type == 'out_invoice' and self.nti_edu_is_tagihan and self.state == 'posted' \
            and self.currency_id.compare_amounts(self.amount_residual, 0.0) > 0

    # --- cicilan ----------------------------------------------------------------------------

    @api.depends('state', 'move_type', 'amount_residual', 'amount_total', 'nti_edu_komponen_id',
                 'nti_edu_tagihan_asal_id')
    def _compute_nti_edu_boleh_cicil(self):
        for move in self:
            komponen = move.nti_edu_komponen_id.sudo()
            move.nti_edu_boleh_cicil = bool(
                move.move_type == 'out_invoice' and move.state == 'posted' and komponen.aturan_cicilan_id
                and komponen.jenis != 'denda' and not move.nti_edu_tagihan_asal_id
                and move.currency_id.compare_amounts(move.amount_total, 0.0) > 0
                and move.currency_id.compare_amounts(move.amount_residual, move.amount_total) == 0)

    def _nti_edu_jadwal_cicilan(self, jumlah_kali):
        """Jadwal cicilan tagihan ini `[(jatuh_tempo, nominal), ...]` menurut aturan cicilan komponennya (spec §4.4).

        Jatuh tempo ke-i = jatuh tempo awal + i × jarak aturan (i = 0..n−1); jatuh tempo awal = jatuh tempo piutang
        paling awal (sama dengan `invoice_date_due` selama tagihan belum dicicil). Nominal: bila ada uang muka,
        cicilan pertama = persen itu dari total dan sisanya dibagi rata, selain itu dibagi rata; dibulatkan ke
        satuan utuh mata uang dengan selisih pembulatan di cicilan terakhir. Dibaca dengan hak pemanggil.
        `UserError` bila komponen tidak boleh dicicil atau `jumlah_kali` di luar 2..maks.
        """
        self.ensure_one()
        komponen = self.nti_edu_komponen_id
        if komponen.jenis == 'denda' or self.nti_edu_tagihan_asal_id:
            raise UserError(_('Tagihan denda %s tidak dapat dicicil.', self.name))
        aturan = komponen.aturan_cicilan_id
        if not aturan:
            raise UserError(_('Komponen %s tidak boleh dicicil.', komponen.name or '-'))
        if not 2 <= jumlah_kali <= aturan.maks_kali:
            raise UserError(_('Jumlah cicilan harus 2 sampai %(maks)s kali menurut aturan "%(aturan)s".',
                              maks=aturan.maks_kali, aturan=aturan.name))
        mata_uang = self.currency_id
        total = self.amount_total
        if aturan.uang_muka_persen:
            pertama = _bulatkan_satuan(mata_uang, total * aturan.uang_muka_persen / 100.0)
            bagian = _bulatkan_satuan(mata_uang, (total - pertama) / (jumlah_kali - 1))
            nominal = [pertama] + [bagian] * (jumlah_kali - 1)
        else:
            nominal = [_bulatkan_satuan(mata_uang, total / jumlah_kali)] * jumlah_kali
        nominal[-1] = mata_uang.round(total - sum(nominal[:-1]))
        if any(mata_uang.compare_amounts(n, 0.0) <= 0 for n in nominal):
            raise UserError(_('Tagihan %(tagihan)s terlalu kecil untuk dicicil %(kali)s kali.',
                              tagihan=self.name, kali=jumlah_kali))

        piutang = self.line_ids.filtered(lambda b: b.account_id.account_type == 'asset_receivable')
        awal = min(piutang.mapped('date_maturity') or [self.invoice_date_due])
        if aturan.jarak_satuan == 'hari':
            langkah = [relativedelta(days=aturan.jarak * i) for i in range(jumlah_kali)]
        else:
            langkah = [relativedelta(months=aturan.jarak * i) for i in range(jumlah_kali)]
        return [(awal + d, n) for d, n in zip(langkah, nominal)]

    @api.model
    def _nti_edu_termin_cicilan(self, tanggal_invoice, jadwal):
        """Termin pembayaran (tanpa unit, sehingga dipakai semua unit) yang dari `tanggal_invoice` menghasilkan
        persis `jadwal`: baris nominal tetap untuk semua cicilan kecuali terakhir, cicilan terakhir = sisa (100%).
        Termin dengan baris identik dipakai ulang. Dibuat sebagai superuser; hak diperiksa pemanggil."""
        baris = []
        for i, (tanggal, nominal) in enumerate(jadwal):
            terakhir = i == len(jadwal) - 1
            baris.append({
                'value': 'percent' if terakhir else 'fixed',
                'value_amount': 100.0 if terakhir else nominal,
                'delay_type': 'days_after',
                'nb_days': (tanggal - tanggal_invoice).days,
            })
        # Nama tidak diterjemahkan agar termin yang sama ditemukan lagi apa pun bahasa pemanggil.
        bagian = ['+%s hari %s' % (b['nb_days'], 'sisa' if b['value'] == 'percent'
                                   else _format_nominal(b['value_amount'])) for b in baris]
        nama = 'Cicilan NTI %s× (%s)' % (len(baris), '; '.join(bagian))
        tanda = [(b['value'], round(b['value_amount'], 6), b['delay_type'], b['nb_days']) for b in baris]

        Termin = self.env['account.payment.term'].sudo()
        for termin in Termin.search([('name', '=', nama), ('company_id', '=', False)]):
            if not termin.early_discount and tanda == [
                    (b.value, round(b.value_amount, 6), b.delay_type, b.nb_days) for b in termin.line_ids]:
                return termin
        return Termin.create({
            'name': nama,
            'company_id': False,
            'early_discount': False,
            'line_ids': [Command.create(b) for b in baris],
        })

    def _nti_edu_atur_cicilan(self, jumlah_kali):
        """Pecah tagihan yang belum dibayar sama sekali menjadi `jumlah_kali` cicilan (spec §4.4): tagihan dikembalikan
        ke draft, diberi termin cicilan, lalu di-post lagi; jadwal dicatat di chatter atas nama pemanggil.

        Hanya Bendahara unit tagihan (atau Admin Keuangan); penulisan sebagai superuser.
        """
        semua = self.sudo()
        self.env['nti_edu.tagihan.akses']._nti_edu_cek_hak(GRUP_BENDAHARA, semua.company_id)
        bukan = semua.filtered(lambda m: m.move_type != 'out_invoice' or not m.nti_edu_is_tagihan)
        if bukan:
            raise UserError(_('%s bukan tagihan sekolah.', self._nti_edu_nama_terlihat(bukan)))
        rencana = []
        for tagihan in semua:
            if tagihan.state != 'posted':
                raise UserError(_('Tagihan %s tidak berstatus terbit sehingga tidak dapat dicicil.', tagihan.name))
            if tagihan.currency_id.compare_amounts(tagihan.amount_residual, tagihan.amount_total) != 0:
                raise UserError(_('Tagihan %s sudah dibayar atau dikoreksi sebagian sehingga tidak dapat dicicil.',
                                  tagihan.name))
            rencana.append((tagihan, tagihan._nti_edu_jadwal_cicilan(jumlah_kali)))

        penulis = self.env.user.partner_id.id
        for tagihan, jadwal in rencana:
            termin = self._nti_edu_termin_cicilan(tagihan.invoice_date, jadwal)
            tagihan.button_draft()
            tagihan.invoice_payment_term_id = termin
            tagihan.action_post()
            piutang = tagihan.line_ids.filtered(lambda b: b.account_id.account_type == 'asset_receivable')
            hasil = [(b.date_maturity, b.amount_currency) for b in piutang.sorted(lambda b: (b.date_maturity, b.id))]
            mata_uang = tagihan.currency_id
            if len(hasil) != len(jadwal) or any(
                    h[0] != j[0] or mata_uang.compare_amounts(h[1], j[1]) != 0 for h, j in zip(hasil, jadwal)):
                raise UserError(_('Jadwal cicilan tagihan %s tidak dapat diterapkan dengan termin pembayaran.',
                                  tagihan.name))
            rincian = Markup('').join(
                Markup('<li>%s: %s</li>') % (format_date(self.env, tanggal), format_amount(self.env, nominal, mata_uang))
                for tanggal, nominal in jadwal)
            tagihan.message_post(
                body=Markup('<p>%s</p><ul>%s</ul>') % (_('Tagihan dicicil %s kali:', jumlah_kali), rincian),
                author_id=penulis)

    # --- kredit siswa -----------------------------------------------------------------------

    @api.depends('state', 'move_type', 'amount_residual', 'commercial_partner_id')
    def _compute_nti_edu_ada_kredit(self):
        for move in self:
            move.nti_edu_ada_kredit = bool(
                move.id and move.nti_edu_is_tagihan and move._nti_edu_kredit_terbuka())

    def _nti_edu_kredit_terbuka(self):
        """Baris piutang kredit terbuka (pembayaran atau nota kredit yang belum terpakai) milik siswa tagihan ini
        yang bisa diterapkan ke tagihan ini, urut tanggal; dibaca sebagai superuser. Kosong bila tagihan bukan
        invoice terbit yang masih bersisa. Domain mengikuti widget "Outstanding credits" Odoo."""
        self.ensure_one()
        move = self.sudo()
        Baris = self.env['account.move.line'].sudo()
        if move.move_type != 'out_invoice' or move.state != 'posted' \
                or move.currency_id.compare_amounts(move.amount_residual, 0.0) <= 0:
            return Baris
        piutang = move.line_ids.filtered(lambda b: b.account_id.account_type == 'asset_receivable')
        if not piutang:
            return Baris
        return Baris.search([
            ('account_id', 'in', piutang.account_id.ids),
            ('parent_state', '=', 'posted'),
            '|', *move._check_company_domain(move.company_id), ('company_id', 'child_of', move.company_id.id),
            ('partner_id', '=', move.commercial_partner_id.id),
            ('reconciled', '=', False),
            ('balance', '<', 0.0),
            ('amount_residual', '!=', 0.0),
        ], order='date, id')

    def action_nti_edu_terapkan_kredit(self):
        """Tombol "Terapkan Kredit" (Bendahara unit): pakai kredit terbuka siswa yang sama untuk melunasi tagihan
        ini, kredit tertua lebih dahulu."""
        semua = self.sudo()
        self.env['nti_edu.tagihan.akses']._nti_edu_cek_hak(GRUP_BENDAHARA, semua.company_id)
        if semua.filtered(lambda m: m.move_type != 'out_invoice' or not m.nti_edu_is_tagihan):
            raise UserError(_('Kredit siswa hanya dapat diterapkan ke tagihan sekolah.'))
        penulis = self.env.user.partner_id.id
        diterapkan = False
        for tagihan in semua:
            sebelum = tagihan.amount_residual
            for baris in tagihan._nti_edu_kredit_terbuka():
                if tagihan.currency_id.compare_amounts(tagihan.amount_residual, 0.0) <= 0:
                    break
                tagihan.js_assign_outstanding_line(baris.id)
            terpakai = sebelum - tagihan.amount_residual
            if tagihan.currency_id.compare_amounts(terpakai, 0.0) > 0:
                diterapkan = True
                tagihan.message_post(body=_(
                    'Kredit siswa sebesar %s diterapkan ke tagihan ini.',
                    format_amount(self.env, terpakai, tagihan.currency_id)), author_id=penulis)
        if not diterapkan:
            raise UserError(_('Tidak ada kredit siswa yang dapat diterapkan ke tagihan ini.'))
        return True

    @api.model
    def _nti_edu_terapkan_potongan(self, potongan):
        """Nota kredit `potongan` (aktif) untuk tagihan terbit siswanya yang belum lunas dalam rentang tanggalnya.

        Per tagihan: jumlah = potongan ini saja atas nominal komponen − potongan jenis yang sama yang sudah ada
        (baris minus tagihan + nota kredit potongan jenis itu), dibatasi sisa tagihan; hanya bila > 0. Nota kredit
        di-post dan direkonsiliasi dengan tagihan; hak pemanggil diperiksa oleh pemanggil.
        """
        potongan.ensure_one()
        pot = potongan.sudo()
        jenis = pot.jenis_id
        Move = self.sudo()
        kandidat = Move.search([
            ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('nti_edu_siswa_id', '=', pot.siswa_id.id),
            ('nti_edu_komponen_id', 'in', jenis.komponen_ids.ids), ('nti_edu_sumber', '=', False),
            ('nti_edu_tagihan_asal_id', '=', False), ('amount_residual', '>', 0),
        ], order='invoice_date, id')
        kandidat = kandidat.filtered(lambda m: pot.tanggal_mulai <= (m.nti_edu_periode or m.invoice_date) and (
            not pot.tanggal_selesai or (m.nti_edu_periode or m.invoice_date) <= pot.tanggal_selesai))
        if not kandidat:
            return self.browse()
        nota_lama = Move.search([
            ('move_type', '=', 'out_refund'), ('state', '!=', 'cancel'), ('reversed_entry_id', 'in', kandidat.ids),
            ('nti_edu_potongan_id.jenis_id', '=', jenis.id)])
        penulis = self.env.user.partner_id.id
        hari_ini = fields.Date.context_today(self)
        hasil = Move.browse()
        for tagihan in kandidat:
            nota_tagihan = nota_lama.filtered(lambda n: n.reversed_entry_id == tagihan)
            if pot in nota_tagihan.nti_edu_potongan_id:
                continue
            mata_uang = tagihan.currency_id
            baris = tagihan.invoice_line_ids
            nominal = sum(baris.filtered(lambda b: b.price_subtotal > 0).mapped('price_subtotal'))
            sudah = -sum(baris.filtered(lambda b: b.nti_edu_potongan_jenis_id == jenis).mapped('price_subtotal'))
            sudah += sum(nota_tagihan.mapped('amount_total'))
            jumlah = min(pot._jumlah(nominal, mata_uang) - sudah, tagihan.amount_residual)
            if mata_uang.compare_amounts(jumlah, 0) <= 0:
                continue
            nota = tagihan._nti_edu_buat_nota_potongan(pot, jumlah, hari_ini)
            hasil |= nota
            nilai = format_amount(self.env, jumlah, mata_uang)
            tagihan.message_post(body=_(
                'Potongan %(jenis)s diterapkan lewat nota kredit %(nota)s sebesar %(nilai)s.',
                jenis=jenis.name, nota=nota.name, nilai=nilai), author_id=penulis)
        if hasil:
            pot.message_post(body=_(
                'Diterapkan ke tagihan terbit: %s.', ', '.join(
                    '%s (%s)' % (n.reversed_entry_id.name, format_amount(self.env, n.amount_total, n.currency_id))
                    for n in hasil)), author_id=penulis)
        return hasil.with_env(self.env)

    def _nti_edu_buat_nota_potongan(self, potongan, jumlah, tanggal):
        """Nota kredit sebesar `jumlah` atas tagihan ini untuk `potongan`, di-post lalu direkonsiliasi (sudo)."""
        self.ensure_one()
        tagihan = self.sudo()
        komponen = tagihan.nti_edu_komponen_id
        nilai_baris = {
            'product_id': komponen.product_id.id,
            'name': _('Potongan %s', potongan.jenis_id.name),
            'quantity': 1,
            'price_unit': jumlah,
            'tax_ids': [Command.clear()],
            'nti_edu_potongan_jenis_id': potongan.jenis_id.id,
        }
        if komponen.akun_pendapatan_id:
            nilai_baris['account_id'] = komponen.akun_pendapatan_id.id
        vals = {
            'move_type': 'out_refund',
            'company_id': tagihan.company_id.id,
            'journal_id': tagihan.journal_id.id,
            'partner_id': tagihan.partner_id.id,
            'invoice_date': tanggal,
            'invoice_payment_term_id': False,
            'reversed_entry_id': tagihan.id,
            'invoice_origin': tagihan.name,
            'ref': _('Potongan %(jenis)s atas %(tagihan)s', jenis=potongan.jenis_id.name, tagihan=tagihan.name),
            'invoice_line_ids': [Command.create(nilai_baris)],
            'nti_edu_siswa_id': tagihan.nti_edu_siswa_id.id,
            'nti_edu_komponen_id': komponen.id,
            'nti_edu_potongan_id': potongan.id,
        }
        try:
            with self.env.cr.savepoint():
                with mute_logger('odoo.sql_db'):
                    nota = tagihan.with_company(tagihan.company_id).create(vals)
                nota.action_post()
        except errors.UniqueViolation as e:
            pesan = self._nti_edu_pesan_ganda(e.diag.constraint_name, tagihan.nti_edu_siswa_id, komponen)
            if not pesan:
                raise
            raise UserError(pesan) from None
        piutang = nota.line_ids.filtered(
            lambda b: b.account_id.account_type == 'asset_receivable' and not b.reconciled)
        if piutang:
            tagihan.js_assign_outstanding_line(piutang[0].id)
        return nota

    @api.model
    def _nti_edu_buat_tagihan(self, siswa, komponen, nominal, sumber, keterangan=None):
        """API jembatan bagi modul lain: tagihan untuk dokumen `sumber` tanpa skema dan potongan.

        Jatuh tempo = hari ini + `hari_jatuh_tempo` periode komponen (0 bila komponen tanpa periode).
        Satu dokumen sumber hanya boleh punya satu tagihan aktif.
        """
        sumber.ensure_one()
        hari_ini = fields.Date.context_today(self)
        hari = komponen.sudo().periode_jenis_id.hari_jatuh_tempo or 0
        return self._nti_edu_terbitkan(
            siswa, komponen, nominal, hari_ini, hari_ini + timedelta(days=hari), keterangan=keterangan,
            sumber='%s,%s' % (sumber._name, sumber.id))


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    nti_edu_potongan_jenis_id = fields.Many2one(
        'nti_edu.tagihan.potongan.jenis', string='Jenis Potongan', readonly=True, copy=False,
        index='btree_not_null', ondelete='restrict',
        help='Jenis potongan siswa yang menjadi dasar baris potongan tagihan atau nota kredit ini.')
