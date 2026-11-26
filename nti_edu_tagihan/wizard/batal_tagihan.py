# -*- coding: utf-8 -*-
from odoo import api, fields, models


class BatalTagihanWizard(models.TransientModel):
    """Batalkan tagihan yang belum dibayar dengan alasan wajib (spec §4.3). Tagihan yang sudah dibayar dikoreksi
    lewat nota kredit standar."""
    _name = 'nti_edu.tagihan.batal.wizard'
    _description = 'Wizard Batalkan Tagihan'

    tagihan_ids = fields.Many2many('account.move', string='Tagihan', required=True, readonly=True)
    alasan = fields.Text(string='Alasan', required=True, help='Dicatat di chatter tiap tagihan yang dibatalkan.')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        konteks = self.env.context
        if 'tagihan_ids' in fields_list and not res.get('tagihan_ids') \
                and konteks.get('active_model') == 'account.move' and konteks.get('active_ids'):
            res['tagihan_ids'] = [(6, 0, konteks['active_ids'])]
        return res

    def action_batal(self):
        self.ensure_one()
        self.tagihan_ids._nti_edu_batalkan(self.alasan)
        return {'type': 'ir.actions.act_window_close'}
