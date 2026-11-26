# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

# Pengaturan kebijakan tagihan per unit; hanya Admin Sistem yang boleh mengubahnya (spec §4.2).
FIELD_PENGATURAN_TAGIHAN = (
    'nti_edu_tagihan_otomatis',
    'nti_edu_tagihan_mulai',
    'nti_edu_denda_saldo_awal',
    'nti_edu_tagihan_jurnal_id',
    'nti_edu_email_tagihan_terbit',
    'nti_edu_pengingat_hari',
    'nti_edu_pengingat_tunggakan',
    'nti_edu_denda_hapus_perlu_admin',
    'nti_edu_wali_kelas_lihat_tunggakan',
    'nti_edu_bukti_ukuran_maks_mb',
    'nti_edu_akses_pembukuan',
)


class ResCompany(models.Model):
    _inherit = 'res.company'

    nti_edu_akses_pembukuan = fields.Selection([
        ('dokumen_sekolah', 'Dokumen Sekolah Saja'),
        ('semua', 'Semua Pembukuan Unit'),
    ], string='Cakupan Pembukuan', required=True, default='dokumen_sekolah',
        help='Yang dilihat Bendahara Unit dan Pemantau Keuangan di unit ini: hanya tagihan siswa dan pembayaran '
             'yang dibuat modul Keuangan Sekolah, atau seluruh invoice, tagihan vendor, pembayaran, dan jurnal unit. '
             'Grup Akuntansi dan Admin Sistem selalu melihat semuanya.')
    nti_edu_tagihan_otomatis = fields.Boolean(
        string='Tagihan Otomatis', help='Jadwal harian menerbitkan tagihan periode yang tanggal terbitnya sudah lewat.')
    nti_edu_tagihan_mulai = fields.Date(
        string='Tagihan Mulai',
        help='Tagihan tidak pernah diterbitkan untuk periode sebelum tanggal ini; wajib sebelum tagihan otomatis '
             'dinyalakan.')
    nti_edu_denda_saldo_awal = fields.Boolean(
        string='Denda untuk Tunggakan Awal', help='Tunggakan saldo awal ikut dikenai denda keterlambatan.')
    nti_edu_tagihan_jurnal_id = fields.Many2one(
        'account.journal', string='Jurnal Tagihan', domain="[('type', '=', 'sale')]",
        help='Jurnal penjualan untuk tagihan siswa; kosong = jurnal penjualan pertama yang berlaku untuk unit.')
    nti_edu_email_tagihan_terbit = fields.Boolean(
        string='Email Saat Tagihan Terbit', default=True)
    nti_edu_pengingat_hari = fields.Integer(
        string='Pengingat (Hari Sebelum Jatuh Tempo)', default=3, help='0 = tanpa pengingat.')
    nti_edu_pengingat_tunggakan = fields.Integer(
        string='Ringkasan Tunggakan Tiap (Hari)', default=0, help='0 = tanpa ringkasan tunggakan.')
    nti_edu_denda_hapus_perlu_admin = fields.Boolean(
        string='Hapus Denda Hanya Admin Keuangan', default=True,
        help='Bila mati, Bendahara Unit boleh menghapus denda dengan alasan.')
    nti_edu_wali_kelas_lihat_tunggakan = fields.Boolean(
        string='Wali Kelas Melihat Tunggakan Rombel')
    nti_edu_bukti_ukuran_maks_mb = fields.Integer(
        string='Ukuran Maksimum Bukti Transfer (MB)', default=5)
    nti_edu_boleh_atur_tagihan = fields.Boolean(
        string='Boleh Mengubah Pengaturan Tagihan', compute='_compute_nti_edu_boleh_atur_tagihan',
        help='Hanya untuk tampilan; penjaga sebenarnya ada di write().')

    @api.depends_context('uid')
    def _compute_nti_edu_boleh_atur_tagihan(self):
        boleh = self.env.su or self.env.user.has_group('base.group_system')
        for rec in self:
            rec.nti_edu_boleh_atur_tagihan = boleh

    @api.constrains('nti_edu_tagihan_otomatis', 'nti_edu_tagihan_mulai')
    def _cek_tagihan_otomatis(self):
        for rec in self:
            if rec.nti_edu_tagihan_otomatis and not rec.nti_edu_tagihan_mulai:
                raise ValidationError(_(
                    'Isi Tagihan Mulai untuk %s sebelum menyalakan tagihan otomatis.', rec.name))

    @api.constrains('nti_edu_pengingat_hari', 'nti_edu_pengingat_tunggakan', 'nti_edu_bukti_ukuran_maks_mb')
    def _cek_angka_tagihan(self):
        for rec in self:
            if rec.nti_edu_pengingat_hari < 0 or rec.nti_edu_pengingat_tunggakan < 0:
                raise ValidationError(_('Jumlah hari pengingat tidak boleh negatif.'))
            if rec.nti_edu_bukti_ukuran_maks_mb <= 0:
                raise ValidationError(_('Ukuran maksimum bukti transfer harus lebih dari 0 MB.'))

    @api.constrains('nti_edu_tagihan_jurnal_id')
    def _cek_jurnal_tagihan(self):
        for rec in self.filtered('nti_edu_tagihan_jurnal_id'):
            jurnal = rec.nti_edu_tagihan_jurnal_id.sudo()
            if jurnal.type != 'sale':
                raise ValidationError(_('Jurnal tagihan "%s" harus jurnal penjualan.', jurnal.name))
            if jurnal.company_id not in rec.sudo().parent_ids:
                raise ValidationError(_(
                    'Jurnal "%(jurnal)s" tidak bisa dipakai unit %(unit)s.', jurnal=jurnal.name, unit=rec.name))

    def write(self, vals):
        if (not self.env.su and not self.env.user.has_group('base.group_system')
                and any(f in vals for f in FIELD_PENGATURAN_TAGIHAN)):
            raise AccessError(_('Pengaturan Keuangan Sekolah hanya dapat diubah Admin Sistem.'))
        return super().write(vals)

    def _nti_edu_jurnal_tagihan(self):
        """Jurnal penjualan untuk tagihan unit ini: pengaturan unit, atau jurnal penjualan pertama yang berlaku
        (milik unit atau induknya)."""
        self.ensure_one()
        Jurnal = self.env['account.journal'].sudo()
        jurnal = self.sudo().nti_edu_tagihan_jurnal_id or Jurnal.search([
            ('type', '=', 'sale'), *Jurnal._check_company_domain(self)], limit=1)
        if not jurnal:
            raise UserError(_('Belum ada jurnal penjualan untuk %s. Hubungi akuntan yayasan.', self.name))
        return jurnal.with_env(self.env)
