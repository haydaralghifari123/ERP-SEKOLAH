# -*- coding: utf-8 -*-
from datetime import timedelta

from psycopg2 import errors

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_amount, mute_logger

GRUP_BENDAHARA = 'nti_edu_tagihan.group_tagihan_bendahara'

# Nilai `**sekolah` yang boleh diberikan ke `_nti_edu_terbitkan`, dipetakan ke field `nti_edu_<nama>`.
FIELD_SEKOLAH = (
    'periode', 'tahun_ajaran_id', 'semester_id', 'rombel_id', 'tagihan_asal_id', 'denda_jatuh_tempo',
    'denda_bulan_ke', 'saldo_awal', 'sumber',
)

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
    nti_edu_lunas = fields.Boolean(string='Lunas', compute='_compute_nti_edu_lunas')

    def init(self):
        super().init()
        for nama, (kolom, syarat) in INDEKS_UNIK.items():
            self.env.cr.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {nama} ON account_move {kolom} "
                f"WHERE state != 'cancel' AND {syarat}")

    @api.depends('nti_edu_komponen_id')
    def _compute_nti_edu_is_tagihan(self):
        for move in self:
            move.nti_edu_is_tagihan = bool(move.nti_edu_komponen_id)

    @api.depends('state', 'amount_residual', 'currency_id')
    def _compute_nti_edu_lunas(self):
        for move in self:
            move.nti_edu_lunas = move.state == 'posted' and move.currency_id.is_zero(move.amount_residual)

    # --- penerbitan --------------------------------------------------------------------------

    @api.model
    def _nti_edu_terbitkan(self, siswa, komponen, nominal, tanggal, jatuh_tempo, potongan=(), keterangan=None,
                           **sekolah):
        """Terbitkan satu tagihan (invoice posted) untuk `siswa` atas `komponen` sebesar `nominal`.

        `potongan`: daftar `(jenis_potongan, jumlah)` yang menjadi baris minus "Potongan <jenis>".
        `sekolah`: nilai field `nti_edu_<nama>` (lihat FIELD_SEKOLAH); record boleh diberikan langsung.
        Hak pemanggil diperiksa oleh pemanggil (`nti_edu.tagihan.akses`); penulisan dilakukan sebagai superuser
        dengan uid pemanggil tetap tercatat. Tagihan ganda → `UserError`.
        """
        siswa.ensure_one()
        if not siswa.sudo().nti_edu_is_siswa:
            raise UserError(_('"%s" bukan siswa sehingga tidak dapat ditagih.', siswa.sudo().display_name))
        company = siswa.sudo().company_id
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
        bukan = semua.filtered(lambda m: m.move_type != 'out_invoice' or not m.nti_edu_is_tagihan)
        if bukan:
            raise UserError(_('%s bukan tagihan sekolah.', ', '.join(bukan.mapped('display_name'))))
        self.env['nti_edu.tagihan.akses']._nti_edu_cek_hak(GRUP_BENDAHARA, semua.company_id)
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
