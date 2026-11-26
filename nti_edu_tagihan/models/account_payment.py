# -*- coding: utf-8 -*-
from odoo import _, fields, models

from .account_move import _field_cek_tanpa_partner


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    nti_edu_dari_tagihan = fields.Boolean(
        string='Pembayaran Tagihan Sekolah', readonly=True, copy=False, index=True,
        help='Dibuat modul Keuangan Sekolah; terlihat oleh Bendahara Unit dan Pemantau Keuangan.')

    def _check_company(self, fnames=None):
        """Payment sekolah untuk siswa yang sudah pindah unit tetap dicatat di unit tagihannya: unit `partner_id`
        tidak diperiksa bila payment dibuat modul (`nti_edu_dari_tagihan`) dan partnernya siswa; field lain dan payment
        lain tetap diperiksa Odoo seperti biasa."""
        sekolah = self.filtered(lambda p: p.nti_edu_dari_tagihan and p.sudo().partner_id.nti_edu_is_siswa)
        if self - sekolah:
            super(AccountPayment, self - sekolah)._check_company(fnames)
        if sekolah:
            super(AccountPayment, sekolah)._check_company(_field_cek_tanpa_partner(self, fnames, ('partner_id',)))

    def _compute_payment_receipt_title(self):
        # Kuitansi pembayaran sekolah memakai laporan tanda terima Odoo dengan judul sendiri; kop = unit payment.
        super()._compute_payment_receipt_title()
        for payment in self.filtered('nti_edu_dari_tagihan'):
            payment.payment_receipt_title = _('Kuitansi Pembayaran')


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    # Payment dari wizard ini ditandai sekolah sejak dibuat (bukan sesudahnya) bila dipanggil `_bayar_baris` dengan
    # konteks `nti_edu_bayar_tagihan`, agar pemeriksaan unit partner siswa pindah unit sudah berlaku saat create.
    def _create_payment_vals_from_wizard(self, batch_result):
        vals = super()._create_payment_vals_from_wizard(batch_result)
        if self.env.context.get('nti_edu_bayar_tagihan'):
            vals['nti_edu_dari_tagihan'] = True
        return vals

    def _create_payment_vals_from_batch(self, batch_result):
        vals = super()._create_payment_vals_from_batch(batch_result)
        if self.env.context.get('nti_edu_bayar_tagihan'):
            vals['nti_edu_dari_tagihan'] = True
        return vals
