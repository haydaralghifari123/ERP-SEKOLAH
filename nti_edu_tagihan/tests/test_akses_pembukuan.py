# -*- coding: utf-8 -*-
from datetime import date

from odoo.exceptions import AccessError
from odoo.tests import Form, tagged
from odoo.tests.common import new_test_user

from .common import NtiTagihanCommon


@tagged('post_install', '-at_install')
class TestAksesPembukuan(NtiTagihanCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.spp = cls._buat_komponen('SPP Akses', 'periode_bulanan')
        Move = cls.env['account.move']
        cls.tagihan_smp = Move._nti_edu_terbitkan(
            cls.siswa_a, cls.spp, 200000, date(2026, 8, 1), date(2026, 8, 10), periode=date(2026, 8, 1))
        cls.tagihan_sma = Move._nti_edu_terbitkan(
            cls.siswa_c, cls.spp, 300000, date(2026, 8, 1), date(2026, 8, 10), periode=date(2026, 8, 1))
        cls.vendor = cls.env['res.partner'].create({'name': 'Toko ATK Tes'})
        cls.vendor_smp = Move.create({
            'move_type': 'in_invoice',
            'company_id': cls.unit_smp.id,
            'partner_id': cls.vendor.id,
            'invoice_date': date(2026, 8, 5),
            'invoice_line_ids': [(0, 0, {'name': 'Kertas', 'quantity': 1, 'price_unit': 50000, 'tax_ids': []})],
        })
        cls.vendor_smp.action_post()
        cls.semua = cls.tagihan_smp | cls.tagihan_sma | cls.vendor_smp
        jurnal_bank = cls.env['account.journal'].search([
            ('company_id', '=', cls.yayasan.id), ('type', '=', 'bank')], limit=1)
        Payment = cls.env['account.payment']
        nilai = {
            'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': cls.siswa_a.id,
            'amount': 50000, 'journal_id': jurnal_bank.id, 'company_id': cls.unit_smp.id,
            'date': date(2026, 8, 6),
        }
        cls.payment_modul = Payment.create(dict(nilai, nti_edu_dari_tagihan=True))
        cls.payment_lain = Payment.create(nilai)
        (cls.payment_modul | cls.payment_lain).action_post()

    def _terlihat(self, user, records):
        return records.with_user(user).search([('id', 'in', records.ids)])

    def test_mode_bawaan(self):
        for user in (self.bendahara_smp, self.pemantau_smp):
            self.assertEqual(self._terlihat(user, self.semua), self.tagihan_smp, user.login)
            self.tagihan_smp.with_user(user).read(['name', 'amount_total'])
            with self.assertRaises(AccessError):
                self.vendor_smp.with_user(user).read(['name'])
            baris = self.semua.line_ids
            self.assertEqual(self._terlihat(user, baris), self.tagihan_smp.line_ids, user.login)
            with self.assertRaises(AccessError):
                self.vendor_smp.line_ids[:1].with_user(user).read(['name'])
            payments = self.payment_modul | self.payment_lain
            self.assertEqual(self._terlihat(user, payments), self.payment_modul, user.login)
            with self.assertRaises(AccessError):
                self.payment_lain.with_user(user).read(['amount'])
            # Entri jurnal milik payment modul ikut terlihat (origin_payment_id), entri payment lain tidak.
            entri = self.payment_modul.move_id | self.payment_lain.move_id
            self.assertEqual(len(entri), 2)
            self.assertEqual(self._terlihat(user, entri), self.payment_modul.move_id, user.login)
            self.assertEqual(self._terlihat(user, entri.line_ids), self.payment_modul.move_id.line_ids, user.login)

    def test_mode_semua(self):
        self.unit_smp.nti_edu_akses_pembukuan = 'semua'
        for user in (self.bendahara_smp, self.pemantau_smp):
            self.assertEqual(self._terlihat(user, self.semua), self.tagihan_smp | self.vendor_smp, user.login)
            self.vendor_smp.with_user(user).read(['name'])
            payments = self.payment_modul | self.payment_lain
            self.assertEqual(self._terlihat(user, payments), payments, user.login)
            with self.assertRaises(AccessError):
                self.tagihan_sma.with_user(user).read(['name'])

    def test_akuntan_selalu_semua(self):
        akuntan = new_test_user(
            self.env, login='tg_akuntan_smp',
            groups='account.group_account_invoice,nti_edu_tagihan.group_tagihan_bendahara',
            company_id=self.unit_smp.id, company_ids=[(6, 0, self.unit_smp.ids)])
        self.assertEqual(self._terlihat(akuntan, self.semua), self.tagihan_smp | self.vendor_smp)
        self.vendor_smp.with_user(akuntan).read(['name'])
        payments = self.payment_modul | self.payment_lain
        self.assertEqual(self._terlihat(akuntan, payments), payments)
        rekonsiliasi = self._lunasi(self.vendor_smp)
        self.assertEqual(self._terlihat(akuntan, rekonsiliasi), rekonsiliasi)

    def test_admin_sistem_selalu_semua(self):
        self.assertEqual(self._terlihat(self.sysadmin, self.semua), self.semua)
        payments = self.payment_modul | self.payment_lain
        self.assertEqual(self._terlihat(self.sysadmin, payments), payments)
        with self.assertRaises(AccessError):
            self.vendor_smp.with_user(self.sysadmin).write({'ref': 'Diubah'})

    def _lunasi(self, move):
        """Lunasi `move` sebagai superuser lewat wizard pembayaran standar; kembalikan rekonsiliasinya."""
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=move.ids).create({'payment_date': date(2026, 8, 7)}
        )._create_payments()
        partials = move.line_ids.matched_debit_ids | move.line_ids.matched_credit_ids
        self.assertTrue(partials)
        return partials

    def test_rekonsiliasi(self):
        rek_tagihan = self._lunasi(self.tagihan_smp)
        rek_vendor = self._lunasi(self.vendor_smp)
        semua_partial = rek_tagihan | rek_vendor
        full = semua_partial.full_reconcile_id
        self.assertEqual(len(full), 2)
        for user in (self.bendahara_smp, self.pemantau_smp):
            self.assertEqual(self._terlihat(user, semua_partial), rek_tagihan, user.login)
            self.assertEqual(self._terlihat(user, full), rek_tagihan.full_reconcile_id, user.login)
            with self.assertRaises(AccessError):
                rek_vendor.with_user(user).read(['amount'])
        self.unit_smp.nti_edu_akses_pembukuan = 'semua'
        self.assertEqual(self._terlihat(self.pemantau_smp, semua_partial), semua_partial)
        self.assertEqual(self._terlihat(self.pemantau_smp, full), full)

    def test_tampilan_pemantau(self):
        """View tagihan, pembayaran, dan pengaturan dapat dibuka pemantau/admin keuangan tanpa galat hak akses."""
        for record, view in (
                (self.tagihan_smp, 'nti_edu_tagihan.view_tagihan_form'),
                (self.payment_modul, 'nti_edu_tagihan.view_pembayaran_form')):
            for user in (self.pemantau_smp, self.bendahara_smp):
                form = Form(record.with_user(user), view=view)
                self.assertTrue(form.name)
        Move = self.env['account.move'].with_user(self.pemantau_smp)
        Move.get_views([(self.env.ref('nti_edu_tagihan.view_tagihan_list').id, 'list'),
                        (self.env.ref('nti_edu_tagihan.view_tagihan_search').id, 'search')])
        Move.web_search_read(
            [('nti_edu_is_tagihan', '=', True)],
            {'name': {}, 'nti_edu_siswa_id': {'fields': {'display_name': {}}}, 'amount_residual': {},
             'payment_state': {}, 'nti_edu_lunas': {}})
        form = Form(self.unit_smp.with_user(self.admin_keu), view='nti_edu_tagihan.view_pengaturan_form')
        self.assertFalse(form.nti_edu_boleh_atur_tagihan)
        with self.assertRaises(AssertionError):
            form.nti_edu_pengingat_hari = 7
        form = Form(self.unit_smp.with_user(self.sysadmin), view='nti_edu_tagihan.view_pengaturan_form')
        self.assertTrue(form.nti_edu_boleh_atur_tagihan)
        form.nti_edu_pengingat_hari = 5
        form.save()
        self.assertEqual(self.unit_smp.nti_edu_pengingat_hari, 5)

    def test_bendahara_tidak_tulis_langsung(self):
        with self.assertRaises(AccessError):
            self.tagihan_smp.with_user(self.bendahara_smp).write({'ref': 'Diubah'})
        with self.assertRaises(AccessError):
            self.env['account.move'].with_user(self.bendahara_smp).create({
                'move_type': 'out_invoice', 'partner_id': self.siswa_a.id, 'company_id': self.unit_smp.id})
        with self.assertRaises(AccessError):
            self.payment_modul.with_user(self.bendahara_smp).write({'amount': 1})
