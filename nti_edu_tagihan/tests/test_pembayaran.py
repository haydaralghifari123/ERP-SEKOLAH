# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, freeze_time, tagged

from .common import NtiTagihanCommon


@tagged('post_install', '-at_install')
class TestPembayaran(NtiTagihanCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Move = cls.env['account.move']
        cls.Payment = cls.env['account.payment']
        cls.Mesin = cls.env['nti_edu.tagihan.mesin']
        cls.spp = cls._buat_komponen('SPP Bayar', 'periode_bulanan')
        cls.rekening_smp = cls._buat_rekening(cls.unit_smp)
        cls.rekening_sma = cls._buat_rekening(cls.unit_sma)

    # --- bantuan ---------------------------------------------------------------------------

    def _terbitkan(self, siswa=None, periode=date(2026, 8, 1), nominal=200000):
        return self.Move._nti_edu_terbitkan(
            siswa or self.siswa_a, self.spp, nominal, periode, periode + timedelta(days=9), periode=periode)

    def _wizard(self, user, siswa=None, **vals):
        Wizard = self.env['nti_edu.tagihan.bayar.wizard'].with_user(user)
        return Wizard.create(dict({'siswa_id': (siswa or self.siswa_a).id, 'tanggal': date(2026, 9, 5)}, **vals))

    def _payments(self, hasil):
        """Pembayaran dari aksi cetak kuitansi yang dikembalikan wizard."""
        self.assertEqual(hasil['type'], 'ir.actions.report')
        self.assertEqual(hasil['report_name'], 'account.report_payment_receipt')
        return self.Payment.browse(hasil['context']['active_ids'])

    def _saldo(self, siswa, user=None):
        """Saldo kredit siswa terkini (field compute tidak tersimpan: cache dibuang lebih dahulu)."""
        siswa.invalidate_recordset(['nti_edu_saldo_kredit'])
        return (siswa.with_user(user) if user else siswa).nti_edu_saldo_kredit

    def _baris_piutang(self, payment):
        return payment.move_id.line_ids.filtered(lambda b: b.account_id.account_type == 'asset_receivable')

    # --- alokasi -----------------------------------------------------------------------------

    def test_alokasi_jatuh_tempo_terlama(self):
        # September dibuat lebih dulu (id lebih kecil): urutan alokasi tetap menurut jatuh tempo.
        sep = self._terbitkan(periode=date(2026, 9, 1))
        agu = self._terbitkan(periode=date(2026, 8, 1))
        payment = self.Mesin._bayar(sep | agu, 300000, self.rekening_smp, date(2026, 9, 5), 'Bayar SPP')
        self.assertEqual(len(payment), 1)
        self.assertTrue(agu.nti_edu_lunas)
        self.assertEqual(agu.amount_residual, 0)
        self.assertFalse(sep.nti_edu_lunas)
        self.assertEqual(sep.amount_residual, 100000)
        self.assertEqual(payment.amount, 300000)
        self.assertEqual(payment.partner_id, self.siswa_a)
        self.assertEqual(payment.journal_id, self.rekening_smp.journal_id)
        self.assertEqual(payment.company_id, self.unit_smp)
        self.assertEqual(payment.date, date(2026, 9, 5))
        self.assertEqual(payment.memo, 'Bayar SPP')
        self.assertEqual(payment.payment_type, 'inbound')
        self.assertTrue(payment.nti_edu_dari_tagihan)
        self.assertIn(payment.state, ('in_process', 'paid'))
        # Seluruh pembayaran terpakai; tidak ada kredit tersisa.
        self.assertFalse(self._baris_piutang(payment).filtered(lambda b: not b.reconciled))
        self.assertEqual(self._saldo(self.siswa_a), 0)

        # Pembayaran berikutnya hanya dialokasikan ke sisa yang masih ada.
        kedua = self.Mesin._bayar(sep | agu, 100000, self.rekening_smp, date(2026, 9, 6), 'Pelunasan')
        self.assertEqual(kedua.amount, 100000)
        self.assertTrue(sep.nti_edu_lunas)
        self.assertEqual(self._saldo(self.siswa_a), 0)

    def test_kelebihan_jadi_kredit(self):
        agu = self._terbitkan(periode=date(2026, 8, 1))
        sep = self._terbitkan(periode=date(2026, 9, 1))
        wizard = self._wizard(self.bendahara_smp)
        # Bawaan: semua tagihan terbuka siswa, nominal = total sisa, rekening unit.
        self.assertEqual(wizard.tagihan_ids, agu | sep)
        self.assertEqual(wizard.total_sisa, 400000)
        self.assertEqual(wizard.nominal, 400000)
        self.assertEqual(wizard.rekening_id, self.rekening_smp)
        wizard.nominal = 500000
        self.assertEqual(wizard.kelebihan, 100000)
        payment = self._payments(wizard.action_bayar())
        self.assertEqual(len(payment), 1)
        self.assertEqual(payment.amount, 500000)
        self.assertTrue(agu.nti_edu_lunas)
        self.assertTrue(sep.nti_edu_lunas)
        self.assertEqual(self._saldo(self.siswa_a, self.bendahara_smp), 100000)

        okt = self._terbitkan(periode=date(2026, 10, 1))
        self.assertTrue(okt.nti_edu_ada_kredit)
        okt.with_user(self.bendahara_smp).action_nti_edu_terapkan_kredit()
        self.assertEqual(okt.amount_residual, 100000)
        self.assertEqual(self._saldo(self.siswa_a), 0)
        self.assertFalse(okt.nti_edu_ada_kredit)
        with self.assertRaisesRegex(UserError, 'kredit'):
            okt.with_user(self.bendahara_smp).action_nti_edu_terapkan_kredit()

    def test_terapkan_kredit_hak(self):
        agu = self._terbitkan(periode=date(2026, 8, 1))
        self.Mesin._bayar(agu, 300000, self.rekening_smp, date(2026, 8, 5), 'Lebih')
        sep = self._terbitkan(periode=date(2026, 9, 1))
        with self.assertRaises(AccessError):
            sep.with_user(self.pemantau_smp).action_nti_edu_terapkan_kredit()
        with self.assertRaises(AccessError):
            sep.with_user(self.bendahara_sma).action_nti_edu_terapkan_kredit()
        self.assertEqual(sep.amount_residual, 200000)
        # Kredit siswa lain tidak dipakai.
        sep_b = self._terbitkan(siswa=self.siswa_b, periode=date(2026, 9, 1))
        self.assertFalse(sep_b.nti_edu_ada_kredit)
        with self.assertRaisesRegex(UserError, 'kredit'):
            sep_b.with_user(self.bendahara_smp).action_nti_edu_terapkan_kredit()
        sep.with_user(self.bendahara_smp).action_nti_edu_terapkan_kredit()
        self.assertEqual(sep.amount_residual, 100000)

    def test_saldo_kredit_nota_kredit(self):
        """Nota kredit potongan yang sudah direkonsiliasi tidak dihitung; nota kredit terbuka dihitung."""
        jenis = self.env['nti_edu.tagihan.potongan.jenis'].create({
            'name': 'Potongan Bayar', 'tipe': 'nominal', 'nilai_bawaan': 50000,
            'komponen_ids': [(6, 0, self.spp.ids)]})
        sep = self._terbitkan(periode=date(2026, 9, 1))
        pot = self.env['nti_edu.tagihan.potongan'].create({
            'siswa_id': self.siswa_a.id, 'jenis_id': jenis.id, 'tanggal_mulai': date(2026, 9, 1)})
        pot.action_ajukan()
        pot.action_terapkan_terbit()
        self.assertEqual(sep.amount_residual, 150000)
        self.assertEqual(self._saldo(self.siswa_a), 0)
        nota = self.Move.create({
            'move_type': 'out_refund', 'company_id': self.unit_smp.id, 'partner_id': self.siswa_a.id,
            'journal_id': self.unit_smp._nti_edu_jurnal_tagihan().id, 'invoice_date': date(2026, 9, 2),
            'invoice_line_ids': [(0, 0, {'name': 'Pengembalian', 'quantity': 1, 'price_unit': 30000,
                                         'tax_ids': [(5, 0, 0)]})]})
        nota.action_post()
        self.assertEqual(self._saldo(self.siswa_a), 30000)
        self.assertEqual(self._saldo(self.siswa_b), 0)

    def test_dua_saudara_satu_unit(self):
        adik = self._buat_siswa('Adik A Tagihan', self.unit_smp, 'TG004')
        t_kakak = self._terbitkan(siswa=self.siswa_a)
        t_adik = self._terbitkan(siswa=adik)
        payments = self.Mesin._bayar(t_kakak | t_adik, 450000, self.rekening_smp, date(2026, 8, 5), 'Kakak adik')
        self.assertEqual(len(payments), 2)
        self.assertEqual(payments.partner_id, self.siswa_a | adik)
        self.assertTrue(all(payments.mapped('nti_edu_dari_tagihan')))
        p_kakak = payments.filtered(lambda p: p.partner_id == self.siswa_a)
        p_adik = payments.filtered(lambda p: p.partner_id == adik)
        self.assertEqual(p_kakak.amount, 200000)
        # Kelebihan ke siswa pertama menurut nama ("Adik ..." < "Siswa ...").
        self.assertEqual(p_adik.amount, 250000)
        self.assertTrue(t_kakak.nti_edu_lunas)
        self.assertTrue(t_adik.nti_edu_lunas)
        self.assertEqual(self._saldo(adik), 50000)
        self.assertEqual(self._saldo(self.siswa_a), 0)
        # Tiap payment hanya direkonsiliasi dengan tagihan siswanya.
        self.assertEqual(p_kakak.reconciled_invoice_ids, t_kakak)
        self.assertEqual(p_adik.reconciled_invoice_ids, t_adik)

    def test_kelebihan_siswa_tanpa_sisa(self):
        """Kelebihan untuk siswa yang tagihannya sudah lunas tetap menjadi kredit siswa itu."""
        adik = self._buat_siswa('Adik B Tagihan', self.unit_smp, 'TG005')
        t_kakak = self._terbitkan(siswa=self.siswa_a)
        t_adik = self._terbitkan(siswa=adik)
        self.Mesin._bayar(t_adik, 200000, self.rekening_smp, date(2026, 8, 4), 'Lunas dulu')
        payments = self.Mesin._bayar(
            t_kakak | t_adik, 260000, self.rekening_smp, date(2026, 8, 5), 'Transfer', siswa_kelebihan=adik)
        self.assertEqual(len(payments), 2)
        self.assertEqual(payments.filtered(lambda p: p.partner_id == adik).amount, 60000)
        self.assertEqual(payments.filtered(lambda p: p.partner_id == self.siswa_a).amount, 200000)
        self.assertTrue(t_kakak.nti_edu_lunas)
        self.assertEqual(self._saldo(adik), 60000)
        with self.assertRaisesRegex(UserError, 'bukan siswa'):
            self.Mesin._bayar(t_kakak, 1000, self.rekening_smp, date(2026, 8, 5), 'x', siswa_kelebihan=self.siswa_b)

    def test_beda_unit_ditolak(self):
        t_smp = self._terbitkan(siswa=self.siswa_a)
        t_sma = self._terbitkan(siswa=self.siswa_c)
        with self.assertRaisesRegex(UserError, 'satu unit'):
            self.Mesin._bayar(t_smp | t_sma, 400000, self.rekening_smp, date(2026, 8, 5), 'Campur')
        # Rekening yang tidak berlaku untuk unit ditolak.
        with self.assertRaisesRegex(UserError, 'Rekening'):
            self.Mesin._bayar(t_smp, 200000, self.rekening_sma, date(2026, 8, 5), 'Rekening salah')
        with self.assertRaisesRegex(UserError, 'lebih dari nol'):
            self.Mesin._bayar(t_smp, 0, self.rekening_smp, date(2026, 8, 5), 'Nol')
        # Tagihan yang tidak terbit dan dokumen yang bukan tagihan ditolak.
        t_batal = self._terbitkan(siswa=self.siswa_b)
        t_batal._nti_edu_batalkan('Salah')
        with self.assertRaisesRegex(UserError, 'terbit'):
            self.Mesin._bayar(t_smp | t_batal, 200000, self.rekening_smp, date(2026, 8, 5), 'Batal')
        bukan = self.Move.create({
            'move_type': 'out_invoice', 'company_id': self.unit_smp.id, 'partner_id': self.siswa_a.id,
            'journal_id': self.unit_smp._nti_edu_jurnal_tagihan().id,
            'invoice_line_ids': [(0, 0, {'name': 'Lain', 'quantity': 1, 'price_unit': 1000})]})
        bukan.action_post()
        with self.assertRaisesRegex(UserError, 'bukan tagihan'):
            self.Mesin._bayar(bukan, 1000, self.rekening_smp, date(2026, 8, 5), 'Bukan')
        self.assertFalse(self.Payment.search([('partner_id', 'in', (self.siswa_a | self.siswa_c).ids)]))
        self.assertEqual(t_smp.amount_residual, 200000)

    def test_wizard_dari_daftar_tagihan(self):
        agu = self._terbitkan(periode=date(2026, 8, 1))
        sep = self._terbitkan(periode=date(2026, 9, 1))
        self._terbitkan(siswa=self.siswa_b)
        Wizard = self.env['nti_edu.tagihan.bayar.wizard'].with_user(self.bendahara_smp)
        with Form(Wizard.with_context(active_model='account.move', active_ids=sep.ids)) as form:
            self.assertEqual(form.siswa_id, self.siswa_a)
            self.assertEqual(form.nominal, 200000)
            form.tanggal = date(2026, 9, 5)
        wizard = form.record
        self.assertEqual(wizard.tagihan_ids, sep)
        self._payments(wizard.action_bayar())
        self.assertTrue(sep.nti_edu_lunas)
        self.assertFalse(agu.nti_edu_lunas)
        # Tagihan dua siswa sekaligus tidak bisa dibayar lewat satu wizard.
        t_b = self.Move.search([('nti_edu_siswa_id', '=', self.siswa_b.id)])
        with self.assertRaisesRegex(UserError, 'satu siswa'):
            Wizard.with_context(active_model='account.move', active_ids=(agu | t_b).ids).create(
                {'tanggal': date(2026, 9, 5)})
        # Tagihan siswa lain di wizard ditolak saat bayar.
        wizard = self._wizard(self.bendahara_smp, tagihan_ids=[(6, 0, t_b.ids)])
        with self.assertRaisesRegex(UserError, 'bukan milik'):
            wizard.action_bayar()

    @freeze_time('2026-09-05')
    def test_hak(self):
        agu = self._terbitkan(periode=date(2026, 8, 1))
        wizard = self._wizard(self.bendahara_smp)
        with self.assertRaises(AccessError):
            wizard.with_user(self.pemantau_smp).action_bayar()
        with self.assertRaises(AccessError):
            self.Mesin.with_user(self.pemantau_smp)._bayar(agu, 200000, self.rekening_smp, date(2026, 9, 5), 'x')
        with self.assertRaises(AccessError):
            self._wizard(self.bendahara_sma).action_bayar()
        self.assertFalse(agu.nti_edu_lunas)

        hasil = wizard.action_bayar()
        payment = self._payments(hasil)
        self.assertTrue(agu.nti_edu_lunas)
        self.assertEqual(payment.date, date(2026, 9, 5))
        self.assertEqual(payment.create_uid, self.bendahara_smp)
        # Mode bawaan (dokumen sekolah): bendahara membaca payment yang dibuatnya, termasuk kuitansinya.
        self.assertEqual(self.unit_smp.nti_edu_akses_pembukuan, 'dokumen_sekolah')
        Payment = self.Payment.with_user(self.bendahara_smp)
        self.assertEqual(Payment.search([('id', 'in', payment.ids)]), payment)
        payment.with_user(self.bendahara_smp).read(['amount', 'partner_id', 'reconciled_invoice_ids'])
        html, _tipe = self.env['ir.actions.report'].with_user(self.bendahara_smp)._render_qweb_html(
            'account.report_payment_receipt', payment.ids)
        html = html.decode()
        self.assertIn('Kuitansi Pembayaran', html)
        self.assertIn(self.unit_smp.name, html)
        self.assertIn(self.siswa_a.name, html)
        # Bendahara unit lain tidak melihatnya.
        self.assertFalse(self.Payment.with_user(self.bendahara_sma).search([('id', 'in', payment.ids)]))
