# -*- coding: utf-8 -*-
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

GRUP_OPERATOR = 'nti_edu_base.group_base_operator'

# Field data siswa yang hanya boleh diubah Operator Data Sekolah (dipakai penjaga tulis).
FIELD_SISWA = {
    'nti_edu_is_siswa', 'nti_edu_nis', 'nti_edu_nisn', 'nti_edu_nik', 'nti_edu_jenis_kelamin',
    'nti_edu_tempat_lahir', 'nti_edu_tanggal_lahir', 'nti_edu_agama', 'nti_edu_status',
    'nti_edu_tanggal_masuk', 'nti_edu_wali_ids',
    'nti_edu_anggota_ids', 'nti_edu_rombel_aktif_id', 'name', 'company_id',
    # Kontak/alamat/foto/arsip siswa: email & telepon kelak jadi kanal undangan portal.
    'email', 'phone', 'mobile', 'street', 'street2', 'zip', 'city', 'state_id', 'country_id',
    'image_1920', 'active',
    # Lewat jalur relasi/sinkronisasi alamat induk-anak dan data komersial.
    'parent_id', 'type', 'child_ids', 'vat', 'function', 'title', 'category_id', 'comment', 'lang',
}


class ResPartner(models.Model):
    _inherit = 'res.partner'

    nti_edu_is_siswa = fields.Boolean(string='Siswa', index=True)
    nti_edu_nis = fields.Char(string='NIS', help='Nomor Induk Siswa (unik per unit)')
    nti_edu_nisn = fields.Char(string='NISN', groups=GRUP_OPERATOR, help='Nomor Induk Siswa Nasional (unik global)')
    nti_edu_nik = fields.Char(string='NIK', groups=GRUP_OPERATOR)
    nti_edu_jenis_kelamin = fields.Selection([('l', 'Laki-laki'), ('p', 'Perempuan')], string='Jenis Kelamin')
    nti_edu_tempat_lahir = fields.Char(string='Tempat Lahir', groups=GRUP_OPERATOR)
    nti_edu_tanggal_lahir = fields.Date(string='Tanggal Lahir', groups=GRUP_OPERATOR)
    nti_edu_agama = fields.Selection([
        ('islam', 'Islam'), ('kristen', 'Kristen'), ('katolik', 'Katolik'), ('hindu', 'Hindu'),
        ('buddha', 'Buddha'), ('konghucu', 'Konghucu'), ('lainnya', 'Lainnya'),
    ], string='Agama', groups=GRUP_OPERATOR)
    nti_edu_status = fields.Selection([
        ('aktif', 'Aktif'), ('lulus', 'Lulus'), ('pindah', 'Pindah'), ('keluar', 'Keluar'),
    ], string='Status Siswa', default='aktif')
    nti_edu_tanggal_masuk = fields.Date(string='Tanggal Masuk')
    nti_edu_wali_ids = fields.One2many('nti_edu.siswa.wali', 'siswa_id', string='Wali', groups=GRUP_OPERATOR)
    nti_edu_anak_ids = fields.One2many('nti_edu.siswa.wali', 'partner_id', string='Anak', groups=GRUP_OPERATOR)
    nti_edu_is_wali = fields.Boolean(string='Adalah Wali', compute='_compute_nti_edu_is_wali', store=True)

    nti_edu_anggota_ids = fields.One2many('nti_edu.rombel.anggota', 'siswa_id', string='Riwayat Kelas')
    nti_edu_rombel_aktif_id = fields.Many2one(
        'nti_edu.rombel', string='Rombel Aktif', compute='_compute_nti_edu_rombel_aktif', store=True)

    @api.depends('nti_edu_anggota_ids.rombel_id.tahun_ajaran_id.is_aktif', 'nti_edu_anggota_ids.tanggal_keluar')
    def _compute_nti_edu_rombel_aktif(self):
        for rec in self:
            aktif = rec.nti_edu_anggota_ids.filtered(
                lambda a: a.rombel_id.tahun_ajaran_id.is_aktif and not a.tanggal_keluar)[:1]
            rec.nti_edu_rombel_aktif_id = aktif.rombel_id

    def _nti_edu_rombel_pada(self, tanggal):
        """Rombel siswa pada tanggal tertentu (kosong bila tidak ada); tanggal keluar dihitung masih anggota."""
        self.ensure_one()
        anggota = self.sudo().nti_edu_anggota_ids.filtered(
            lambda a: a.tahun_ajaran_id.tanggal_mulai <= tanggal <= a.tahun_ajaran_id.tanggal_selesai
            and (not a.tanggal_masuk or a.tanggal_masuk <= tanggal)
            and (not a.tanggal_keluar or a.tanggal_keluar > tanggal))
        # Bila masih ada beberapa, pilih yang paling akhir masuk.
        anggota = anggota.sorted(lambda a: (a.tanggal_masuk or date.min, a.id), reverse=True)[:1]
        return anggota.rombel_id

    @api.constrains('company_id')
    def _check_nti_edu_unit_keanggotaan(self):
        for rec in self.sudo().filtered('nti_edu_is_siswa'):
            if rec.nti_edu_anggota_ids.filtered(
                    lambda a: not a.tanggal_keluar and a.company_id != rec.company_id):
                raise ValidationError(_(
                    'Siswa "%s" masih menjadi anggota rombel pada unit lain; keluarkan dahulu dari rombel tersebut.',
                    rec.name))

    @api.depends('nti_edu_anak_ids')
    def _compute_nti_edu_is_wali(self):
        for rec in self:
            rec.nti_edu_is_wali = bool(rec.nti_edu_anak_ids)

    # --- Constraint (Python: company bisa NULL di partner lain, jadi bukan SQL unique) ---

    @api.constrains('nti_edu_is_siswa', 'company_id')
    def _check_nti_edu_siswa_unit(self):
        for rec in self:
            if rec.nti_edu_is_siswa and not rec.company_id:
                raise ValidationError(_("Siswa harus terdaftar pada satu unit sekolah."))

    @api.constrains('nti_edu_nis', 'company_id')
    def _check_nti_edu_nis_unik(self):
        Partner = self.env['res.partner'].sudo().with_context(active_test=False)
        for rec in self.sudo().filtered('nti_edu_nis'):
            ganda = Partner.search_count([
                ('id', '!=', rec.id), ('nti_edu_nis', '=', rec.nti_edu_nis),
                ('company_id', '=', rec.company_id.id or False)])
            if ganda:
                raise ValidationError(_("NIS %s sudah dipakai siswa lain pada unit yang sama.", rec.nti_edu_nis))

    @api.constrains('nti_edu_nisn')
    def _check_nti_edu_nisn_unik(self):
        Partner = self.env['res.partner'].sudo().with_context(active_test=False)
        for rec in self.sudo().filtered('nti_edu_nisn'):
            if Partner.search_count([('id', '!=', rec.id), ('nti_edu_nisn', '=', rec.nti_edu_nisn)]):
                raise ValidationError(_("NISN %s sudah dipakai siswa lain.", rec.nti_edu_nisn))

    # --- Penjaga tulis: data siswa hanya untuk Operator Data Sekolah ---

    def _nti_edu_perlu_operator(self):
        return not self.env.su and not self.env.user.has_group(GRUP_OPERATOR)

    def _nti_edu_tolak(self):
        raise AccessError(_("Hanya Operator Data Sekolah yang boleh mengubah data siswa."))

    @api.model_create_multi
    def create(self, vals_list):
        if self._nti_edu_perlu_operator():
            bawaan = self.env.context.get('default_nti_edu_is_siswa')
            Partner = self.env['res.partner'].sudo()
            if any(vals.get('nti_edu_is_siswa', bawaan)
                   or (vals.get('parent_id') and Partner.browse(vals['parent_id']).nti_edu_is_siswa)
                   for vals in vals_list):
                self._nti_edu_tolak()
        return super().create(vals_list)

    def write(self, vals):
        if self and self._nti_edu_perlu_operator() and FIELD_SISWA & set(vals):
            if vals.get('nti_edu_is_siswa') or any(self.sudo().mapped('nti_edu_is_siswa')):
                self._nti_edu_tolak()
        return super().write(vals)

    def unlink(self):
        if self and self._nti_edu_perlu_operator() and any(self.sudo().mapped('nti_edu_is_siswa')):
            self._nti_edu_tolak()
        return super().unlink()

    def update_address(self, vals):
        # Jalur sinkronisasi alamat bawaan memanggil write dasar (melewati penjaga di atas).
        if self and self._nti_edu_perlu_operator() and any(self.sudo().mapped('nti_edu_is_siswa')):
            self._nti_edu_tolak()
        return super().update_address(vals)

    # --- Akun portal ---

    def _nti_edu_login_default(self):
        """Login bawaan akun portal: siswa = NISN atau "<kode unit>.<NIS>"; wali = email atau telepon."""
        self.ensure_one()
        if self.nti_edu_is_siswa:
            nisn = (self.nti_edu_nisn or '').strip()
            if nisn:
                return nisn
            kode = (self.company_id.nti_edu_kode or '').strip()
            nis = (self.nti_edu_nis or '').strip()
            if not kode or not nis:
                raise UserError(_(
                    "Login siswa %s tidak bisa dibuat: isi NISN, atau kode unit dan NIS.", self.display_name))
            return f"{kode}.{nis}"
        login = (self.email or '').strip() or (self.phone or '').strip()
        if not login:
            raise UserError(_("%s belum punya email atau telepon untuk dijadikan login.", self.display_name))
        return login

    def action_nti_edu_buat_akun_portal(self):
        self.ensure_one()
        if not self.env.user.has_group(GRUP_OPERATOR):
            raise AccessError(_("Hanya Operator Data Sekolah yang boleh membuat akun portal."))
        return {
            'type': 'ir.actions.act_window',
            'name': _("Buat Akun Portal"),
            'res_model': 'nti_edu.akun.portal.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_partner_id': self.id},
        }
