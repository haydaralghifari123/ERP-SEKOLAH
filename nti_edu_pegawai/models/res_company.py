# -*- coding: utf-8 -*-
from odoo import _, api, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.constrains('nti_edu_jenis')
    def _check_nti_edu_jenis_berpegawai(self):
        # Pegawai wajib berada di unit sekolah: unit yang masih punya pegawai aktif tetap unit.
        Pegawai = self.env['hr.employee'].sudo()
        for rec in self.filtered(lambda c: c.nti_edu_jenis != 'unit'):
            if Pegawai.search_count([('company_id', '=', rec.id)]):
                raise ValidationError(_(
                    "Jenis entitas tidak bisa diubah menjadi bukan unit karena masih memiliki pegawai aktif."))
