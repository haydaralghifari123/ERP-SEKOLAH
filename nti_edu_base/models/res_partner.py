# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

GRUP_OPERATOR = 'nti_edu_base.group_base_operator'

# Field data siswa yang hanya boleh diubah Operator Data Sekolah (dipakai penjaga tulis).
FIELD_SISWA = {
    'nti_edu_is_siswa', 'nti_edu_nis', 'nti_edu_nisn', 'nti_edu_nik', 'nti_edu_jenis_kelamin',
    'nti_edu_tempat_lahir', 'nti_edu_tanggal_lahir', 'nti_edu_agama', 'nti_edu_status',
    'nti_edu_tanggal_masuk', 'nti_edu_wali_ids', 'name', 'company_id',
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
    nti_edu_anak_ids = fields.One2many('nti_edu.siswa.wali', 'partner_id', string='Anak')
    nti_edu_is_wali = fields.Boolean(string='Adalah Wali', compute='_compute_nti_edu_is_wali', store=True)

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
            if any(vals.get('nti_edu_is_siswa', bawaan) for vals in vals_list):
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
