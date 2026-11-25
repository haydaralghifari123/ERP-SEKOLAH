# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    nti_edu_jenis_ptk = fields.Selection([
        ('guru_mapel', 'Guru Mapel'), ('guru_kelas', 'Guru Kelas'), ('guru_bk', 'Guru BK'),
        ('kepala_sekolah', 'Kepala Sekolah'), ('wakil_kepala', 'Wakil Kepala'),
        ('tendik_admin', 'Tenaga Administrasi'), ('pustakawan', 'Pustakawan'),
        ('laboran', 'Laboran'), ('lainnya', 'Lainnya'),
    ], string='Jenis PTK')
    nti_edu_tmt = fields.Date(string='TMT di Unit Ini')

    @api.constrains('company_id')
    def _check_nti_edu_pegawai_unit(self):
        for rec in self.sudo():
            if rec.company_id.nti_edu_jenis != 'unit':
                raise ValidationError(_("Pegawai harus terdaftar pada unit sekolah, bukan yayasan."))
