# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

from .res_partner import GRUP_HRD, GRUP_OPERATOR

# Field profil per orang yang dicerminkan (dapat diedit) pada form pegawai.
PROFIL_TERKAIT = (
    'nti_edu_nik', 'nti_edu_nuptk', 'nti_edu_nip', 'nti_edu_status_kepegawaian',
    'nti_edu_pendidikan_terakhir', 'nti_edu_bidang_studi',
)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    nti_edu_jenis_ptk = fields.Selection([
        ('guru_mapel', 'Guru Mapel'), ('guru_kelas', 'Guru Kelas'), ('guru_bk', 'Guru BK'),
        ('kepala_sekolah', 'Kepala Sekolah'), ('wakil_kepala', 'Wakil Kepala'),
        ('tendik_admin', 'Tenaga Administrasi'), ('pustakawan', 'Pustakawan'),
        ('laboran', 'Laboran'), ('lainnya', 'Lainnya'),
    ], string='Jenis PTK')
    nti_edu_tmt = fields.Date(string='TMT di Unit Ini')

    # Profil per orang: disimpan pada kontak kerja (satu per orang, terlihat di semua unit).
    nti_edu_nik = fields.Char(
        string='NIK', compute='_compute_nti_edu_profil', inverse='_inverse_nti_edu_profil', groups=GRUP_OPERATOR)
    nti_edu_nuptk = fields.Char(
        string='NUPTK', compute='_compute_nti_edu_profil', inverse='_inverse_nti_edu_profil', groups=GRUP_OPERATOR)
    nti_edu_nip = fields.Char(
        string='NIP', compute='_compute_nti_edu_profil', inverse='_inverse_nti_edu_profil', groups=GRUP_OPERATOR)
    nti_edu_status_kepegawaian = fields.Selection(
        selection=lambda self: self.env['res.partner']._fields['nti_edu_status_kepegawaian'].selection,
        string='Status Kepegawaian', compute='_compute_nti_edu_profil', inverse='_inverse_nti_edu_profil',
        groups=GRUP_OPERATOR)
    nti_edu_pendidikan_terakhir = fields.Selection(
        selection=lambda self: self.env['res.partner']._fields['nti_edu_pendidikan_terakhir'].selection,
        string='Pendidikan Terakhir', compute='_compute_nti_edu_profil', inverse='_inverse_nti_edu_profil',
        groups=GRUP_OPERATOR)
    nti_edu_bidang_studi = fields.Char(
        string='Bidang Studi', compute='_compute_nti_edu_profil', inverse='_inverse_nti_edu_profil',
        groups=GRUP_OPERATOR)

    @api.constrains('company_id')
    def _check_nti_edu_pegawai_unit(self):
        for rec in self.sudo():
            if rec.company_id.nti_edu_jenis != 'unit':
                raise ValidationError(_("Pegawai harus terdaftar pada unit sekolah, bukan yayasan."))

    @api.depends('work_contact_id', *('work_contact_id.' + f for f in PROFIL_TERKAIT))
    def _compute_nti_edu_profil(self):
        for rec in self:
            kontak = rec.work_contact_id.sudo()
            for f in PROFIL_TERKAIT:
                rec[f] = kontak[f]

    def _inverse_nti_edu_profil(self):
        Partner = self.env['res.partner']
        for rec in self:
            if not rec.work_contact_id:
                continue
            if not Partner.browse(rec.work_contact_id.id)._nti_edu_boleh_ubah_profil_pegawai():
                Partner._nti_edu_tolak_profil()
            rec.work_contact_id.sudo().write({f: rec[f] for f in PROFIL_TERKAIT})

    # --- Penjaga: akun login dan hapus hanya HRD ---

    def _nti_edu_perlu_hrd(self):
        return not self.env.su and not self.env.user.has_group(GRUP_HRD)

    def _nti_edu_cek_tautan_kontak(self, kontak_id):
        """Kontak yang sudah jadi pegawai di unit lain tidak boleh ditautkan oleh TU yang tak memegang unit itu."""
        if not kontak_id:
            return
        pegawai = self.env['hr.employee'].sudo().search([
            ('work_contact_id', '=', kontak_id), ('id', 'not in', self.ids)])
        if not pegawai.company_id <= self.env.user.company_ids:
            raise AccessError(_("Menempatkan pegawai dari unit lain hanya boleh oleh HRD atau TU yang memegang kedua unit."))

    @api.model_create_multi
    def create(self, vals_list):
        if self._nti_edu_perlu_hrd():
            if any(vals.get('user_id') for vals in vals_list):
                raise AccessError(_("Akun login pegawai hanya boleh ditautkan oleh HRD."))
            for vals in vals_list:
                self._nti_edu_cek_tautan_kontak(vals.get('work_contact_id'))
        return super().create(vals_list)

    def write(self, vals):
        if self._nti_edu_perlu_hrd():
            if 'user_id' in vals:
                raise AccessError(_("Akun login pegawai hanya boleh ditautkan oleh HRD."))
            self._nti_edu_cek_tautan_kontak(vals.get('work_contact_id'))
        return super().write(vals)

    def unlink(self):
        if self._nti_edu_perlu_hrd():
            raise AccessError(_("Pegawai hanya boleh dihapus oleh HRD. Arsipkan pegawai ini bila sudah tidak aktif."))
        return super().unlink()
