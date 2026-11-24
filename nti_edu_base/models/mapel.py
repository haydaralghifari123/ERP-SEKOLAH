# -*- coding: utf-8 -*-
from odoo import fields, models


class Mapel(models.Model):
    _name = 'nti_edu.mapel'
    _description = 'Mata Pelajaran'
    _order = 'name'

    name = fields.Char(string='Nama', required=True)
    kode = fields.Char(string='Kode')
    kelompok = fields.Selection([
        ('umum', 'Umum'), ('kejuruan', 'Kejuruan'), ('mulok', 'Muatan Lokal'),
    ], string='Kelompok')
    company_id = fields.Many2one('res.company', string='Unit Sekolah')
