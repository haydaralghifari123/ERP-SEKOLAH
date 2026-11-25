# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    def write(self, vals):
        # Pegawai di unit = pegawai unit, di yayasan = staf yayasan (hanya HRD): company yang masih punya pegawai
        # aktif tidak boleh berganti jenis (unit <-> yayasan). Jenis lama dibaca sebelum ditulis; dicek sesudah
        # super agar penjaga hak tulis company tetap lebih dulu.
        berubah = self.browse()
        if 'nti_edu_jenis' in vals:
            berubah = self.sudo().filtered(lambda c: c.nti_edu_jenis != vals['nti_edu_jenis'])
        hasil = super().write(vals)
        if berubah and self.env['hr.employee'].sudo().search_count([('company_id', 'in', berubah.ids)]):
            raise ValidationError(_("Jenis entitas tidak bisa diubah karena masih memiliki pegawai aktif."))
        return hasil
