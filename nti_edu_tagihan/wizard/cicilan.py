# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_amount, format_date


class CicilanWizard(models.TransientModel):
    """Pecah tagihan yang belum dibayar menjadi cicilan menurut aturan cicilan komponennya (spec §4.4)."""
    _name = 'nti_edu.tagihan.cicilan.wizard'
    _description = 'Wizard Atur Cicilan'

    tagihan_id = fields.Many2one('account.move', string='Tagihan', required=True, readonly=True)
    aturan_id = fields.Many2one(
        'nti_edu.tagihan.aturan.cicilan', string='Aturan Cicilan',
        related='tagihan_id.nti_edu_komponen_id.aturan_cicilan_id')
    jumlah_kali = fields.Integer(string='Jumlah Cicilan', required=True, help='Bawaan: maksimum menurut aturan.')
    pratinjau = fields.Html(string='Jadwal', compute='_compute_pratinjau', sanitize=False)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        konteks = self.env.context
        if 'tagihan_id' in fields_list and not res.get('tagihan_id') \
                and konteks.get('active_model') == 'account.move' and konteks.get('active_id'):
            res['tagihan_id'] = konteks['active_id']
        if 'jumlah_kali' in fields_list and not res.get('jumlah_kali'):
            tagihan = self.env['account.move'].browse(res.get('tagihan_id'))
            res['jumlah_kali'] = tagihan.nti_edu_komponen_id.aturan_cicilan_id.maks_kali or 2
        return res

    @api.depends('tagihan_id', 'jumlah_kali')
    def _compute_pratinjau(self):
        for wizard in self:
            tagihan = wizard.tagihan_id
            if not tagihan:
                wizard.pratinjau = False
                continue
            try:
                jadwal = tagihan._nti_edu_jadwal_cicilan(wizard.jumlah_kali)
            except UserError as e:
                wizard.pratinjau = Markup('<p class="text-danger">%s</p>') % e.args[0]
                continue
            baris = Markup('').join(
                Markup('<tr><td>%s</td><td>%s</td><td class="text-end">%s</td></tr>') % (
                    ke, format_date(self.env, tanggal), format_amount(self.env, nominal, tagihan.currency_id))
                for ke, (tanggal, nominal) in enumerate(jadwal, 1))
            wizard.pratinjau = Markup(
                '<table class="table table-sm"><thead><tr><th>%s</th><th>%s</th><th class="text-end">%s</th></tr>'
                '</thead><tbody>%s</tbody></table>') % (_('Ke'), _('Jatuh Tempo'), _('Nominal'), baris)

    def action_atur(self):
        self.ensure_one()
        self.tagihan_id._nti_edu_atur_cicilan(self.jumlah_kali)
        return {'type': 'ir.actions.act_window_close'}
