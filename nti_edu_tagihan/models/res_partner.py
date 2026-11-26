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

    def _nti_edu_penerima_tagihan(self):
        """Penerima email tagihan siswa-siswa ini (spec §4.9): per siswa, wali penanggung biaya yang punya email;
        bila tidak ada, wali kontak utama yang punya email; bila tidak ada, tidak seorang pun. Baris wali dibaca
        sebagai superuser; hasil dalam env pemanggil."""
        penerima = self.browse()
        Wali = self.env['nti_edu.siswa.wali'].sudo()
        for siswa in self.sudo().filtered('nti_edu_is_siswa'):
            baris = Wali.search([('siswa_id', '=', siswa.id)]).filtered(lambda w: w.partner_id.email)
            pilihan = baris.filtered('is_penanggung_biaya') or baris.filtered('is_kontak_utama')
            penerima |= pilihan.partner_id.with_env(self.env)
        return penerima
