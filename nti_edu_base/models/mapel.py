# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.models import to_company_ids
from odoo.tools.misc import unquote


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

    @api.model
    def _check_company_domain(self, companies):
        """Master boleh tanpa company, milik yayasan (induk), atau milik unit pemakai."""
        if not companies:
            return [('company_id', '=', False)]
        ids = unquote(companies) if isinstance(companies, unquote) else to_company_ids(companies)
        return ['|', ('company_id', '=', False), ('company_id', 'parent_of', ids)]
