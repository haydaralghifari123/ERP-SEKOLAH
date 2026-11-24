# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Ruang(models.Model):
    _name = 'nti_edu.ruang'
    _description = 'Ruang'
    _order = 'name'

    name = fields.Char(string='Nama', required=True)
    kode = fields.Char(string='Kode')
    jenis = fields.Selection([
        ('kelas', 'Ruang Kelas'), ('lab', 'Laboratorium'), ('aula', 'Aula'),
        ('lapangan', 'Lapangan'), ('lainnya', 'Lainnya'),
    ], string='Jenis', default='kelas')
    kapasitas = fields.Integer(string='Kapasitas')
    company_id = fields.Many2one(
        'res.company', string='Unit Sekolah', required=True, default=lambda self: self.env.company)

    @api.constrains('company_id')
    def _check_company_unit(self):
        for rec in self.sudo():
            if rec.company_id.nti_edu_jenis != 'unit':
                raise ValidationError(_('"%s" harus milik unit sekolah, bukan yayasan.', rec.display_name))
