# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SiswaWali(models.Model):
    _name = 'nti_edu.siswa.wali'
    _description = 'Wali Siswa'
    _order = 'siswa_id, hubungan'

    siswa_id = fields.Many2one(
        'res.partner', string='Siswa', required=True, ondelete='cascade', index=True,
        domain=[('nti_edu_is_siswa', '=', True)])
    partner_id = fields.Many2one(
        'res.partner', string='Wali', required=True, ondelete='restrict', index=True,
        domain=[('nti_edu_is_siswa', '=', False)])
    hubungan = fields.Selection(
        [('ayah', 'Ayah'), ('ibu', 'Ibu'), ('wali', 'Wali')], string='Hubungan', required=True, default='wali')
    is_kontak_utama = fields.Boolean(string='Kontak Utama')
    is_penanggung_biaya = fields.Boolean(string='Penanggung Biaya')

    _sql_constraints = [
        ('siswa_wali_unik', 'unique(siswa_id, partner_id)', 'Wali yang sama sudah tercatat untuk siswa ini.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        baris = super().create(vals_list)
        # Wali dipakai lintas unit: kosongkan company partner wali (bukan siswa, bukan user internal).
        for wali in baris.sudo().mapped('partner_id'):
            if wali.company_id and not wali.nti_edu_is_siswa and not any(not u.share for u in wali.user_ids):
                # Pemanggil harus berhak menulis partner itu (aturan record / ACL), bukan sekadar sudo.
                wali.with_env(self.env).check_access('write')
                wali.company_id = False
        return baris
