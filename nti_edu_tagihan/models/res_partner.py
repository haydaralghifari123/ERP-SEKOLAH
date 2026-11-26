# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    nti_edu_saldo_kredit = fields.Monetary(
        string='Saldo Kredit', compute='_compute_nti_edu_saldo_kredit', currency_field='currency_id',
        groups='nti_edu_tagihan.group_tagihan_pemantau',
        help='Pembayaran atau nota kredit siswa yang belum terpakai untuk tagihan (kredit piutang terbuka).')

    def _compute_nti_edu_saldo_kredit(self):
        # Dibaca sebagai superuser: saldo siswa mencakup kredit dari dokumen di luar cakupan pembukuan pembaca.
        siswa = self.filtered(lambda p: p._origin.id and p.nti_edu_is_siswa)
        saldo = {}
        if siswa:
            data = self.env['account.move.line'].sudo()._read_group([
                ('partner_id', 'in', siswa._origin.ids),
                ('account_type', '=', 'asset_receivable'),
                ('parent_state', '=', 'posted'),
                ('reconciled', '=', False),
                ('balance', '<', 0.0),
            ], ['partner_id'], ['amount_residual:sum'])
            saldo = {partner.id: -total for partner, total in data}
        for partner in self:
            partner.nti_edu_saldo_kredit = saldo.get(partner._origin.id, 0.0)
