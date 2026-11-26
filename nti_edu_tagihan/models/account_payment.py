# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    nti_edu_dari_tagihan = fields.Boolean(
        string='Pembayaran Tagihan Sekolah', readonly=True, copy=False, index=True,
        help='Dibuat modul Keuangan Sekolah; terlihat oleh Bendahara Unit dan Pemantau Keuangan.')
