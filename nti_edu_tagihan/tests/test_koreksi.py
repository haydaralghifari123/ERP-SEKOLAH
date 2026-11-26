# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, freeze_time, tagged

from .common import NtiTagihanCommon


@tagged('post_install', '-at_install')
class TestKoreksi(NtiTagihanCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Move = cls.env['account.move']
        cls.spp = cls._buat_komponen('SPP Koreksi', 'periode_bulanan')
        cls.pangkal = cls._buat_komponen('Pangkal Koreksi', 'periode_sekali')
        Jenis = cls.env['nti_edu.tagihan.potongan.jenis']
        cls.prestasi = Jenis.create({
            'name': 'Beasiswa Prestasi', 'tipe': 'persen', 'nilai_bawaan': 100, 'perlu_persetujuan': True,
            'komponen_ids': [(6, 0, cls.spp.ids)]})
        cls.saudara = Jenis.create({
            'name': 'Saudara Kandung', 'tipe': 'persen', 'nilai_bawaan': 25,
            'komponen_ids': [(6, 0, cls.spp.ids)]})

    # --- bantuan ---------------------------------------------------------------------------

    def _terbitkan(self, siswa=None, komponen=None, nominal=200000, periode=date(2026, 8, 1), potongan=()):
        return self.Move._nti_edu_terbitkan(
            siswa or self.siswa_a, komponen or self.spp, nominal, periode, periode + timedelta(days=9),
            potongan=potongan, periode=periode)

    def _bayar(self, tagihan, jumlah=None):
        """Bayar `tagihan` sebagai superuser lewat wizard pembayaran standar (penuh bila `jumlah` kosong)."""
        nilai = {'payment_date': tagihan.invoice_date}
        if jumlah is not None:
            nilai['amount'] = jumlah
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=tagihan.ids).create(nilai)._create_payments()

    def _batal_wizard(self, tagihan, user, alasan='Salah nominal'):
        return self.env['nti_edu.tagihan.batal.wizard'].with_user(user).with_context(
            active_model='account.move', active_ids=tagihan.ids).create({'alasan': alasan})

    def _nota(self, tagihan):
        return self.Move.search([
            ('move_type', '=', 'out_refund'), ('reversed_entry_id', 'in', tagihan.ids), ('state', '!=', 'cancel')])

    def _potongan(self, jenis, mulai=date(2026, 8, 1), selesai=False, siswa=None, nilai=None):
        vals = {'siswa_id': (siswa or self.siswa_a).id, 'jenis_id': jenis.id, 'tanggal_mulai': mulai,
                'tanggal_selesai': selesai}
        if nilai is not None:
            vals['nilai'] = nilai
        return self.env['nti_edu.tagihan.potongan'].create(vals)

    # --- batal -----------------------------------------------------------------------------

    def test_batal_belum_bayar(self):
        tagihan = self._terbitkan()
        wizard = self._batal_wizard(tagihan, self.bendahara_smp, alasan='Nominal salah ketik')
        self.assertEqual(wizard.tagihan_ids, tagihan)
        wizard.action_batal()
        self.assertEqual(tagihan.state, 'cancel')
        pesan = tagihan.message_ids.filtered(lambda m: 'Nominal salah ketik' in (m.body or ''))
        self.assertEqual(len(pesan), 1)
        self.assertEqual(pesan.author_id, self.bendahara_smp.partner_id)
        # Tagihan yang sama bisa diterbitkan ulang.
        ulang = self._terbitkan(nominal=175000)
        self.assertEqual(ulang.state, 'posted')
        self.assertEqual(ulang.amount_total, 175000)

    def test_batal_sudah_bayar_ditolak(self):
        tagihan = self._terbitkan()
        self._bayar(tagihan, 50000)
        self.assertEqual(tagihan.amount_residual, 150000)
        with self.assertRaisesRegex(UserError, 'nota kredit'):
            self._batal_wizard(tagihan, self.bendahara_smp).action_batal()
        self.assertEqual(tagihan.state, 'posted')

    def test_batal_hak(self):
        tagihan = self._terbitkan()
        # Bendahara unit lain dan pemantau tidak boleh; alasan wajib.
        with self.assertRaises(AccessError):
            self._batal_wizard(tagihan, self.bendahara_sma).action_batal()
        with self.assertRaises(AccessError):
            self._batal_wizard(tagihan, self.pemantau_smp).action_batal()
        with self.assertRaisesRegex(UserError, 'Alasan'):
            self._batal_wizard(tagihan, self.bendahara_smp, alasan='  ').action_batal()
        # Dokumen yang bukan tagihan sekolah ditolak.
        bukan = self.Move.create({
            'move_type': 'out_invoice', 'company_id': self.unit_smp.id, 'partner_id': self.siswa_a.id,
            'journal_id': self.unit_smp._nti_edu_jurnal_tagihan().id,
            'invoice_line_ids': [(0, 0, {'name': 'Lain', 'quantity': 1, 'price_unit': 1000})]})
        bukan.action_post()
        with self.assertRaises(UserError):
            self._batal_wizard(bukan, self.admin_keu).action_batal()
        self.assertEqual(tagihan.state, 'posted')
        self.assertEqual(bukan.state, 'posted')

    # --- tunggakan awal --------------------------------------------------------------------

    def test_saldo_awal(self):
        self._terbitkan(periode=date(2026, 7, 1))
        Wizard = self.env['nti_edu.tagihan.saldo.awal.wizard'].with_user(self.bendahara_smp)
        with Form(Wizard) as form:
            with form.baris_ids.new() as baris:
                baris.siswa_id = self.siswa_a
                baris.komponen_id = self.spp
                baris.periode = date(2026, 5, 1)
                self.assertEqual(baris.jatuh_tempo, date(2026, 5, 1))
                baris.jatuh_tempo = date(2026, 5, 10)
                baris.nominal = 150000
            with form.baris_ids.new() as baris:
                baris.siswa_id = self.siswa_b
                baris.komponen_id = self.pangkal
                baris.periode = date(2026, 4, 1)
                baris.nominal = 500000
            with form.baris_ids.new() as baris:
                # Duplikat tagihan Juli yang sudah terbit.
                baris.siswa_id = self.siswa_a
                baris.komponen_id = self.spp
                baris.periode = date(2026, 7, 1)
                baris.nominal = 200000
        wizard = form.record
        hasil = wizard.action_simpan()

        mei = self.Move.search([
            ('nti_edu_siswa_id', '=', self.siswa_a.id), ('nti_edu_periode', '=', date(2026, 5, 1))])
        self.assertEqual(len(mei), 1)
        self.assertTrue(mei.nti_edu_saldo_awal)
        self.assertEqual(mei.state, 'posted')
        self.assertEqual(mei.amount_total, 150000)
        self.assertEqual(mei.invoice_date_due, date(2026, 5, 10))
        pangkal = self.Move.search([
            ('nti_edu_siswa_id', '=', self.siswa_b.id), ('nti_edu_komponen_id', '=', self.pangkal.id)])
        self.assertEqual(len(pangkal), 1)
        self.assertTrue(pangkal.nti_edu_saldo_awal)
        # Komponen sekali: tanpa periode, sehingga ikut indeks sekali seumur hidup.
        self.assertFalse(pangkal.nti_edu_periode)
        self.assertEqual(pangkal.invoice_date_due, date(2026, 4, 1))

        # Baris duplikat gagal sendiri dan dilaporkan; baris lain tetap dibuat.
        juli = self.Move.search([
            ('nti_edu_siswa_id', '=', self.siswa_a.id), ('nti_edu_periode', '=', date(2026, 7, 1))])
        self.assertEqual(len(juli), 1)
        self.assertFalse(juli.nti_edu_saldo_awal)
        self.assertEqual(len(wizard.baris_ids), 1)
        self.assertIn('sudah ada', wizard.baris_ids.galat)
        self.assertEqual(hasil['res_model'], 'nti_edu.tagihan.saldo.awal.wizard')
        self.assertEqual(hasil['res_id'], wizard.id)

    def test_saldo_awal_setelah_tagihan_mulai(self):
        """Tunggakan awal harus sebelum Tagihan Mulai unit (periode, atau tanggal untuk komponen sekali)."""
        self.unit_smp.nti_edu_tagihan_mulai = date(2026, 7, 1)
        Wizard = self.env['nti_edu.tagihan.saldo.awal.wizard'].with_user(self.admin_keu)
        wizard = Wizard.create({'baris_ids': [
            (0, 0, {'siswa_id': self.siswa_a.id, 'komponen_id': self.spp.id, 'periode': date(2026, 7, 1),
                    'nominal': 100000}),
            (0, 0, {'siswa_id': self.siswa_a.id, 'komponen_id': self.spp.id, 'periode': date(2026, 6, 1),
                    'nominal': 100000}),
            (0, 0, {'siswa_id': self.siswa_b.id, 'komponen_id': self.pangkal.id, 'periode': date(2026, 8, 1),
                    'nominal': 500000}),
            (0, 0, {'siswa_id': self.siswa_b.id, 'komponen_id': self.pangkal.id, 'jatuh_tempo': date(2026, 7, 5),
                    'nominal': 500000}),
            # Unit SMA tanpa Tagihan Mulai: tidak dibatasi.
            (0, 0, {'siswa_id': self.siswa_c.id, 'komponen_id': self.spp.id, 'periode': date(2026, 9, 1),
                    'nominal': 100000}),
        ]})
        wizard.action_simpan()
        self.assertEqual(len(wizard.baris_ids), 3)
        for baris in wizard.baris_ids:
            self.assertIn('sebelum tanggal mulai tagih', baris.galat)
        juni = self.Move.search([('nti_edu_siswa_id', '=', self.siswa_a.id)])
        self.assertEqual(juni.nti_edu_periode, date(2026, 6, 1))
        self.assertFalse(self.Move.search([('nti_edu_siswa_id', '=', self.siswa_b.id)]))
        self.assertTrue(self.Move.search([('nti_edu_siswa_id', '=', self.siswa_c.id)]).nti_edu_saldo_awal)

    def test_batal_bukan_tagihan_tidak_bocor(self):
        """Hak diperiksa lebih dulu; nama dokumen yang tidak boleh dibaca pemanggil tidak muncul di pesan galat."""
        bukan = self.Move.create({
            'move_type': 'out_invoice', 'company_id': self.unit_smp.id, 'partner_id': self.siswa_a.id,
            'journal_id': self.unit_smp._nti_edu_jurnal_tagihan().id,
            'invoice_line_ids': [(0, 0, {'name': 'Rahasia', 'quantity': 1, 'price_unit': 1000})]})
        bukan.action_post()
        self.assertTrue(bukan.name)
        with self.assertRaises(AccessError):
            bukan.with_user(self.pemantau_smp)._nti_edu_batalkan('x')
        with self.assertRaises(AccessError):
            bukan.with_user(self.bendahara_sma)._nti_edu_batalkan('x')
        with self.assertRaises(UserError) as galat:
            bukan.with_user(self.bendahara_smp)._nti_edu_batalkan('x')
        self.assertNotIn(bukan.name, str(galat.exception))
        self.assertIn('bukan tagihan sekolah', str(galat.exception))
        # Admin Sistem boleh membaca semua entri: nama disebut.
        with self.assertRaises(UserError) as galat:
            bukan.with_user(self.sysadmin)._nti_edu_batalkan('x')
        self.assertIn(bukan.name, str(galat.exception))
        self.assertEqual(bukan.state, 'posted')

    def test_saldo_awal_hak(self):
        Wizard = self.env['nti_edu.tagihan.saldo.awal.wizard']
        vals = {'baris_ids': [(0, 0, {
            'siswa_id': self.siswa_c.id, 'komponen_id': self.spp.id, 'periode': date(2026, 5, 1),
            'nominal': 100000})]}
        with self.assertRaisesRegex(AccessError, 'akses ke unit'):
            Wizard.with_user(self.bendahara_smp).create(vals).action_simpan()
        with self.assertRaises(AccessError):
            Wizard.with_user(self.pemantau_smp).create(vals)
        self.assertFalse(self.Move.search([('nti_edu_siswa_id', '=', self.siswa_c.id)]))
        hasil = Wizard.with_user(self.admin_keu).create(vals).action_simpan()
        self.assertEqual(hasil['type'], 'ir.actions.client')
        self.assertTrue(self.Move.search([('nti_edu_siswa_id', '=', self.siswa_c.id)]).nti_edu_saldo_awal)

    # --- potongan mundur -------------------------------------------------------------------

    def test_potongan_mundur(self):
        agu = self._terbitkan(periode=date(2026, 8, 1))
        sep = self._terbitkan(periode=date(2026, 9, 1))
        self._bayar(agu)
        self.assertEqual(agu.amount_residual, 0)
        pot = self._potongan(self.prestasi, mulai=date(2026, 8, 1))
        pot.with_user(self.bendahara_smp).action_ajukan()
        self.assertEqual(pot.state, 'menunggu')
        pot.with_user(self.admin_keu).action_setujui()
        self.assertEqual(pot.state, 'aktif')
        # Persetujuan tidak mengubah tagihan yang sudah terbit secara diam-diam.
        self.assertEqual((agu.amount_total, agu.amount_residual), (200000, 0))
        self.assertEqual((sep.amount_total, sep.amount_residual), (200000, 200000))
        self.assertFalse(self._nota(agu | sep))

        pot.with_user(self.bendahara_smp).action_terapkan_terbit()
        nota = self._nota(sep)
        self.assertEqual(len(nota), 1)
        self.assertEqual(nota.state, 'posted')
        self.assertEqual(nota.amount_total, 200000)
        self.assertEqual(nota.nti_edu_potongan_id, pot)
        self.assertEqual(nota.nti_edu_komponen_id, self.spp)
        self.assertEqual(nota.nti_edu_siswa_id, self.siswa_a)
        self.assertEqual(nota.invoice_line_ids.name, 'Potongan Beasiswa Prestasi')
        self.assertEqual(nota.invoice_line_ids.product_id, self.spp.product_id)
        self.assertEqual(sep.amount_residual, 0)
        self.assertTrue(sep.nti_edu_lunas)
        # Agustus sudah lunas: tidak disentuh.
        self.assertFalse(self._nota(agu))
        self.assertEqual(agu.amount_total, 200000)
        self.assertTrue(any('Beasiswa Prestasi' in (m.body or '') for m in sep.message_ids))
        self.assertTrue(any(sep.name in (m.body or '') for m in pot.message_ids))

        # Tombol kedua kali tidak membuat nota kredit baru.
        pot.with_user(self.bendahara_smp).action_terapkan_terbit()
        self.assertEqual(self._nota(agu | sep), nota)

    def test_potongan_mundur_selisih(self):
        """Potongan jenis yang sudah ada di tagihan hanya ditambah selisihnya; sisa tagihan membatasi nota."""
        sep = self._terbitkan(periode=date(2026, 9, 1), potongan=[(self.saudara, 50000)])
        okt = self._terbitkan(periode=date(2026, 10, 1))
        nov = self._terbitkan(periode=date(2026, 11, 1))
        des = self._terbitkan(periode=date(2026, 12, 1))
        self._bayar(okt, 180000)
        pot = self._potongan(self.saudara, mulai=date(2026, 9, 1), selesai=date(2026, 11, 30), nilai=40)
        pot.action_ajukan()
        pot.with_user(self.admin_keu).action_terapkan_terbit()
        # September: 40% = 80.000, sudah 50.000 di tagihan → selisih 30.000.
        self.assertEqual(self._nota(sep).amount_total, 30000)
        self.assertEqual(sep.amount_residual, 120000)
        # Oktober: sisa 20.000 membatasi nota kredit.
        self.assertEqual(self._nota(okt).amount_total, 20000)
        self.assertEqual(okt.amount_residual, 0)
        self.assertEqual(self._nota(nov).amount_total, 80000)
        # Desember di luar rentang potongan.
        self.assertFalse(self._nota(des))

    def test_potongan_mundur_hak(self):
        sep = self._terbitkan(periode=date(2026, 9, 1))
        pot = self._potongan(self.saudara)
        # Hanya potongan aktif.
        with self.assertRaises(UserError):
            pot.with_user(self.bendahara_smp).action_terapkan_terbit()
        pot.action_ajukan()
        with self.assertRaises(AccessError):
            pot.with_user(self.pemantau_smp).action_terapkan_terbit()
        with self.assertRaises(AccessError):
            pot.with_user(self.bendahara_sma).action_terapkan_terbit()
        self.assertFalse(self._nota(sep))

    # --- penjaga potongan ------------------------------------------------------------------

    def test_potongan_siswa_unit_lain(self):
        pot = self.env['nti_edu.tagihan.potongan'].with_user(self.bendahara_smp).create({
            'siswa_id': self.siswa_a.id, 'jenis_id': self.saudara.id, 'tanggal_mulai': date(2026, 8, 1)})
        with self.assertRaisesRegex(AccessError, 'di luar unit'):
            pot.write({'siswa_id': self.siswa_c.id})
        self.assertEqual(pot.siswa_id, self.siswa_a)
        pot.write({'siswa_id': self.siswa_b.id})
        self.assertEqual(pot.company_id, self.unit_smp)

    def test_jenis_potongan_unit_lain(self):
        jenis_sma = self.env['nti_edu.tagihan.potongan.jenis'].create({
            'name': 'Khusus SMA', 'tipe': 'nominal', 'nilai_bawaan': 10000, 'company_id': self.unit_sma.id,
            'komponen_ids': [(6, 0, self.spp.ids)]})
        jenis_yayasan = self.env['nti_edu.tagihan.potongan.jenis'].create({
            'name': 'Yayasan', 'tipe': 'nominal', 'nilai_bawaan': 10000, 'company_id': self.yayasan.id,
            'komponen_ids': [(6, 0, self.spp.ids)]})
        with self.assertRaises(ValidationError):
            self._potongan(jenis_sma)
        self._potongan(jenis_sma, siswa=self.siswa_c)
        self._potongan(jenis_yayasan)
        pot = self._potongan(self.saudara)
        with self.assertRaises(ValidationError):
            pot.jenis_id = jenis_sma
        # Mengubah unit jenis yang sudah dipakai siswa unit lain juga ditolak.
        with self.assertRaises(ValidationError):
            jenis_yayasan.company_id = self.unit_sma

    @freeze_time('2026-10-05')
    def test_tanggal_nota(self):
        sep = self._terbitkan(periode=date(2026, 9, 1))
        pot = self._potongan(self.saudara, mulai=date(2026, 9, 1))
        pot.action_ajukan()
        pot.action_terapkan_terbit()
        nota = self._nota(sep)
        self.assertEqual(nota.invoice_date, date(2026, 10, 5))
        self.assertEqual(nota.amount_total, 50000)
