# -*- coding: utf-8 -*-
from odoo import fields, models


class Jurusan(models.Model):
    _name = 'nti_edu.jurusan'
    _description = 'Jurusan'
    _order = 'name'

    name = fields.Char(string='Nama', required=True)
    kode = fields.Char(string='Kode')
    jenjang_id = fields.Many2one('nti_edu.jenjang', string='Jenjang')
    company_id = fields.Many2one('res.company', string='Unit Sekolah', ondelete='cascade')

    # Master boleh tanpa company, milik yayasan (induk), atau milik unit pemakai.
    _check_company_domain = models.check_company_domain_parent_of
