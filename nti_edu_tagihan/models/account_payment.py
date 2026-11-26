# -*- coding: utf-8 -*-
from odoo import _, fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    nti_edu_dari_tagihan = fields.Boolean(
        string='Pembayaran Tagihan Sekolah', readonly=True, copy=False, index=True,
        help='Dibuat modul Keuangan Sekolah; terlihat oleh Bendahara Unit dan Pemantau Keuangan.')

    def _compute_payment_receipt_title(self):
        # Kuitansi pembayaran sekolah memakai laporan tanda terima Odoo dengan judul sendiri; kop = unit payment.
        super()._compute_payment_receipt_title()
        for payment in self.filtered('nti_edu_dari_tagihan'):
            payment.payment_receipt_title = _('Kuitansi Pembayaran')
