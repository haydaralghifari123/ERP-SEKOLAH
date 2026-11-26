# -*- coding: utf-8 -*-
from datetime import date

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tools import format_amount

from .common import NtiTagihanCommon


@tagged('post_install', '-at_install')
class TestCicilan(NtiTagihanCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Move = cls.env['account.move']
        Aturan = cls.env['nti_edu.tagihan.aturan.cicilan']
        cls.aturan_4 = Aturan.create({
            'name': 'Cicil 4x Tes', 'maks_kali': 4, 'jarak': 1, 'jarak_satuan': 'bulan'})
        cls.aturan_dp = Aturan.create({
            'name': 'Cicil DP 40% Tes', 'maks_kali': 3, 'jarak': 30, 'jarak_satuan': 'hari',
            'uang_muka_persen': 40})
        cls.pangkal = cls._buat_komponen(
            'Uang Pangkal Cicil', 'periode_sekali', aturan_cicilan_id=cls.aturan_4.id)
        cls.gedung = cls._buat_komponen(
            'Uang Gedung Cicil', 'periode_sekali', aturan_cicilan_id=cls.aturan_dp.id)
        cls.seragam = cls._buat_komponen('Seragam Tanpa Cicil', 'periode_sekali')
        cls.denda = cls._buat_komponen('Denda Cicil', None, jenis='denda', aturan_cicilan_id=cls.aturan_4.id)
        cls.rekening_smp = cls._buat_rekening(cls.unit_smp)

    # --- bantuan ---------------------------------------------------------------------------

    def _terbitkan(self, komponen=None, siswa=None, nominal=1000000, tanggal=date(2026, 7, 1),
                   jatuh_tempo=date(2026, 7, 10)):
        return self.Move._nti_edu_terbitkan(siswa or self.siswa_a, komponen or self.pangkal, nominal, tanggal,
                                            jatuh_tempo)

    def _jadwal(self, tagihan):
        piutang = tagihan.line_ids.filtered(lambda b: b.account_id.account_type == 'asset_receivable')
        return [(b.date_maturity, b.debit) for b in piutang.sorted(lambda b: (b.date_maturity, b.id))]

    # --- pembagian & jatuh tempo ----------------------------------------------------------------

    def test_cicil_rata(self):
        tagihan = self._terbitkan()
        self.assertTrue(tagihan.with_user(self.bendahara_smp).nti_edu_boleh_cicil)
        nama = tagihan.name
        tagihan.with_user(self.bendahara_smp)._nti_edu_atur_cicilan(4)
        self.assertEqual(tagihan.state, 'posted')
        self.assertEqual(tagihan.name, nama)
        self.assertEqual(tagihan.amount_total, 1000000)
        self.assertEqual(tagihan.amount_residual, 1000000)
        self.assertEqual(self._jadwal(tagihan), [
            (date(2026, 7, 10), 250000), (date(2026, 8, 10), 250000),
            (date(2026, 9, 10), 250000), (date(2026, 10, 10), 250000)])
        termin = tagihan.invoice_payment_term_id
        self.assertTrue(termin.name.startswith('Cicilan NTI 4'))
        self.assertTrue(termin.active)
        self.assertFalse(termin.company_id)
        pesan = tagihan.message_ids.filtered(lambda m: 'icil' in (m.body or ''))
        self.assertTrue(pesan)
        self.assertEqual(pesan[0].author_id, self.bendahara_smp.partner_id)

        # Jadwal yang sama dipakai ulang tanpa membuat termin baru.
        jumlah_termin = self.env['account.payment.term'].with_context(active_test=False).search_count([])
        lain = self._terbitkan(siswa=self.siswa_b)
        lain.with_user(self.bendahara_smp)._nti_edu_atur_cicilan(4)
        self.assertEqual(lain.invoice_payment_term_id, termin)
        self.assertEqual(
            self.env['account.payment.term'].with_context(active_test=False).search_count([]), jumlah_termin)

    def test_cicil_uang_muka(self):
        tagihan = self._terbitkan(komponen=self.gedung)
        wizard = self.env['nti_edu.tagihan.cicilan.wizard'].with_user(self.bendahara_smp).with_context(
            active_model='account.move', active_id=tagihan.id, active_ids=tagihan.ids).create({})
        self.assertEqual(wizard.tagihan_id, tagihan)
        self.assertEqual(wizard.jumlah_kali, 3)
        for nominal in (400000, 300000):
            self.assertIn(format_amount(wizard.env, nominal, tagihan.currency_id), wizard.pratinjau)
        # Jumlah di luar aturan tidak memunculkan jadwal.
        wizard.jumlah_kali = 4
        self.assertIn('text-danger', wizard.pratinjau)
        wizard.jumlah_kali = 3
        wizard.action_atur()
        self.assertEqual(self._jadwal(tagihan), [
            (date(2026, 7, 10), 400000), (date(2026, 8, 9), 300000), (date(2026, 9, 8), 300000)])
        self.assertEqual(tagihan.amount_residual, 1000000)

    def test_pembulatan(self):
        # Terbit dan jatuh tempo di hari yang sama: cicilan pertama 0 hari setelah tanggal terbit.
        tagihan = self._terbitkan(tanggal=date(2026, 7, 10))
        tagihan.with_user(self.bendahara_smp)._nti_edu_atur_cicilan(3)
        jadwal = self._jadwal(tagihan)
        self.assertEqual(jadwal, [
            (date(2026, 7, 10), 333333), (date(2026, 8, 10), 333333), (date(2026, 9, 10), 333334)])
        self.assertEqual(sum(j[1] for j in jadwal), 1000000)
        self.assertEqual(tagihan.amount_total, 1000000)

    def test_akhir_bulan(self):
        # Jarak bulanan dari tanggal 31 dipangkas ke akhir bulan.
        tagihan = self._terbitkan(jatuh_tempo=date(2026, 8, 31))
        tagihan.with_user(self.bendahara_smp)._nti_edu_atur_cicilan(2)
        self.assertEqual(self._jadwal(tagihan), [(date(2026, 8, 31), 500000), (date(2026, 9, 30), 500000)])

    # --- syarat ---------------------------------------------------------------------------------

    def test_syarat(self):
        bendahara = self.bendahara_smp
        tanpa_aturan = self._terbitkan(komponen=self.seragam)
        self.assertFalse(tanpa_aturan.nti_edu_boleh_cicil)
        with self.assertRaises(UserError):
            tanpa_aturan.with_user(bendahara)._nti_edu_atur_cicilan(2)

        tagihan = self._terbitkan()
        with self.assertRaises(UserError):
            tagihan.with_user(bendahara)._nti_edu_atur_cicilan(5)
        with self.assertRaises(UserError):
            tagihan.with_user(bendahara)._nti_edu_atur_cicilan(1)

        with self.assertRaises(AccessError):
            tagihan.with_user(self.pemantau_smp)._nti_edu_atur_cicilan(2)
        with self.assertRaises(AccessError):
            tagihan.with_user(self.bendahara_sma)._nti_edu_atur_cicilan(2)
        self.assertFalse(tagihan.invoice_payment_term_id)

        denda = self._terbitkan(komponen=self.denda, siswa=self.siswa_b, nominal=10000)
        self.assertFalse(denda.nti_edu_boleh_cicil)
        with self.assertRaises(UserError):
            denda.with_user(bendahara)._nti_edu_atur_cicilan(2)

        self.env['nti_edu.tagihan.mesin']._bayar(tagihan, 100000, self.rekening_smp, date(2026, 7, 5), 'DP')
        self.assertEqual(tagihan.amount_residual, 900000)
        self.assertFalse(tagihan.nti_edu_boleh_cicil)
        with self.assertRaises(UserError):
            tagihan.with_user(bendahara)._nti_edu_atur_cicilan(2)
        self.assertFalse(tagihan.invoice_payment_term_id)
        self.assertEqual(tagihan.state, 'posted')

        batal = self._terbitkan(siswa=self.siswa_b)
        batal._nti_edu_batalkan('Salah')
        with self.assertRaises(UserError):
            batal.with_user(bendahara)._nti_edu_atur_cicilan(2)
