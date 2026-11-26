# -*- coding: utf-8 -*-
from odoo import api, fields, models


class TolakKonfirmasiWizard(models.TransientModel):
    """Tolak konfirmasi transfer dengan alasan dari master (spec §4.6); catatan wajib bila alasan
    mewajibkannya. Pemeriksaan hak dan status ada di `nti_edu.tagihan.konfirmasi._tolak`."""
    _name = 'nti_edu.tagihan.tolak.wizard'
    _description = 'Wizard Tolak Konfirmasi Transfer'

    konfirmasi_id = fields.Many2one(
        'nti_edu.tagihan.konfirmasi', string='Konfirmasi Transfer', required=True, readonly=True,
        ondelete='cascade')
    company_id = fields.Many2one(related='konfirmasi_id.company_id', string='Unit Sekolah')
    alasan_id = fields.Many2one(
        'nti_edu.tagihan.alasan.tolak', string='Alasan', required=True,
        domain="['|', ('company_id', '=', False), ('company_id', 'parent_of', company_id)]")
    perlu_catatan = fields.Boolean(related='alasan_id.perlu_catatan', string='Perlu Catatan')
    catatan = fields.Text(string='Catatan', help='Ditampilkan kepada pengirim di portal dan email.')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        konteks = self.env.context
        if 'konfirmasi_id' in fields_list and not res.get('konfirmasi_id') \
                and konteks.get('active_model') == 'nti_edu.tagihan.konfirmasi' and konteks.get('active_id'):
            res['konfirmasi_id'] = konteks['active_id']
        return res

    def action_tolak(self):
        self.ensure_one()
        self.konfirmasi_id._tolak(self.alasan_id, self.catatan)
        return {'type': 'ir.actions.act_window_close'}
