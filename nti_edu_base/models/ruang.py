# -*- coding: utf-8 -*-
from odoo import fields, models


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
