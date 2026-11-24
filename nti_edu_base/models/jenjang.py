# -*- coding: utf-8 -*-
from odoo import fields, models


class Jenjang(models.Model):
    _name = 'nti_edu.jenjang'
    _description = 'Jenjang Pendidikan'
    _order = 'urutan, id'

    name = fields.Char(string='Nama', required=True)
    kode = fields.Char(string='Kode', required=True)
    urutan = fields.Integer(string='Urutan', default=10)
    tingkat_ids = fields.One2many('nti_edu.tingkat', 'jenjang_id', string='Tingkat')

    _sql_constraints = [
        ('kode_unik', 'unique(kode)', 'Kode jenjang harus unik.'),
    ]


class Tingkat(models.Model):
    _name = 'nti_edu.tingkat'
    _description = 'Tingkat Kelas'
    _order = 'jenjang_id, urutan, id'

    name = fields.Char(string='Nama', required=True)
    jenjang_id = fields.Many2one('nti_edu.jenjang', string='Jenjang', required=True, ondelete='cascade')
    urutan = fields.Integer(string='Urutan', default=1)
    is_akhir = fields.Boolean(string='Tingkat Akhir')
