# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HapusDendaWizard(models.TransientModel):
    """Hapus denda keterlambatan yang belum dibayar dengan alasan dari master (spec §4.5); catatan wajib bila
    alasan mewajibkannya. Pemeriksaan hak dan status ada di `account.move._nti_edu_hapus_denda`."""
    _name = 'nti_edu.tagihan.hapus.denda.wizard'
    _description = 'Wizard Hapus Denda'

    tagihan_ids = fields.Many2many('account.move', string='Denda', required=True, readonly=True)
    alasan_id = fields.Many2one('nti_edu.tagihan.alasan.hapus', string='Alasan', required=True)
    perlu_catatan = fields.Boolean(related='alasan_id.perlu_catatan', string='Perlu Catatan')
    catatan = fields.Text(string='Catatan', help='Dicatat di chatter tiap denda yang dihapus.')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        konteks = self.env.context
        if 'tagihan_ids' in fields_list and not res.get('tagihan_ids') \
                and konteks.get('active_model') == 'account.move' and konteks.get('active_ids'):
            res['tagihan_ids'] = [(6, 0, konteks['active_ids'])]
        return res

    def action_hapus(self):
        self.ensure_one()
        self.tagihan_ids._nti_edu_hapus_denda(self.alasan_id, self.catatan)
        return {'type': 'ir.actions.act_window_close'}
