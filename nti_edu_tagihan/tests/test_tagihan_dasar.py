# -*- coding: utf-8 -*-
from datetime import date, timedelta
from unittest.mock import patch

from psycopg2.errors import UniqueViolation

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import freeze_time, tagged
from odoo.tests.common import new_test_user
from odoo.tools import mute_logger

from .common import NtiTagihanCommon


@tagged('post_install', '-at_install')
class TestTagihanDasar(NtiTagihanCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.spp = cls._buat_komponen('SPP Dasar', 'periode_bulanan')
        cls.pangkal = cls._buat_komponen('Pangkal Dasar', 'periode_sekali')
        cls.saudara = cls.env['nti_edu.tagihan.potongan.jenis'].create({
            'name': 'Saudara Kandung', 'tipe': 'nominal', 'nilai_bawaan': 20000,
            'komponen_ids': [(6, 0, cls.spp.ids)]})
        cls.Move = cls.env['account.move']

    def _terbitkan(self, siswa=None, komponen=None, nominal=200000, periode=date(2026, 8, 1), potongan=(),
                   **sekolah):
        komponen = komponen or self.spp
        if periode:
            sekolah.setdefault('periode', periode)
        return self.Move._nti_edu_terbitkan(
            siswa or self.siswa_a, komponen, nominal, periode or date(2026, 7, 1),
            (periode or date(2026, 7, 1)) + timedelta(days=9), potongan=potongan, **sekolah)

    def test_terbitkan(self):
        tagihan = self._terbitkan(
            potongan=[(self.saudara, 20000)], tahun_ajaran_id=self.ta, semester_id=self.semester_ganjil,
            rombel_id=self.rombel_7a)
        self.assertEqual(tagihan.state, 'posted')
        self.assertEqual(tagihan.move_type, 'out_invoice')
        self.assertEqual(tagihan.partner_id, self.siswa_a)
        self.assertEqual(tagihan.nti_edu_siswa_id, self.siswa_a)
        self.assertEqual(tagihan.company_id, self.unit_smp)
        self.assertEqual(tagihan.journal_id, self.unit_smp._nti_edu_jurnal_tagihan())
        self.assertEqual(len(tagihan.invoice_line_ids), 2)
        self.assertEqual(tagihan.amount_total, 180000)
        self.assertEqual(tagihan.invoice_date, date(2026, 8, 1))
        self.assertEqual(tagihan.invoice_date_due, date(2026, 8, 10))
        baris_potongan = tagihan.invoice_line_ids.filtered(lambda b: b.price_unit < 0)
        self.assertEqual(baris_potongan.name, 'Potongan Saudara Kandung')
        self.assertEqual(baris_potongan.price_subtotal, -20000)
        self.assertEqual(tagihan.invoice_line_ids.product_id, self.spp.product_id)
        self.assertFalse(tagihan.invoice_line_ids.tax_ids)
        self.assertEqual(tagihan.nti_edu_komponen_id, self.spp)
        self.assertEqual(tagihan.nti_edu_periode, date(2026, 8, 1))
        self.assertEqual(tagihan.nti_edu_tahun_ajaran_id, self.ta)
        self.assertEqual(tagihan.nti_edu_semester_id, self.semester_ganjil)
        self.assertEqual(tagihan.nti_edu_rombel_id, self.rombel_7a)
        self.assertTrue(tagihan.nti_edu_is_tagihan)
        self.assertFalse(tagihan.nti_edu_lunas)

    def test_akun_pendapatan_komponen(self):
        akun = self.env['account.account'].create({
            'name': 'Pendapatan SPP Tes', 'code': '499001', 'account_type': 'income',
            'company_ids': [(6, 0, self.yayasan.ids)]})
        komponen = self._buat_komponen('SPP Berakun', 'periode_bulanan', akun_pendapatan_id=akun.id)
        self.saudara.komponen_ids = [(4, komponen.id)]
        tagihan = self._terbitkan(komponen=komponen, potongan=[(self.saudara, 20000)])
        self.assertEqual(tagihan.invoice_line_ids.account_id, akun)

    def test_cegah_ganda(self):
        pertama = self._terbitkan()
        with self.assertRaisesRegex(UserError, 'sudah ada'):
            self._terbitkan()
        with self.assertRaisesRegex(UserError, 'sudah ada'):
            self._terbitkan(nominal=150000)
        # Periode lain dan siswa lain boleh.
        self._terbitkan(periode=date(2026, 9, 1))
        self._terbitkan(siswa=self.siswa_b)
        pertama.button_draft()
        pertama.button_cancel()
        ulang = self._terbitkan()
        self.assertEqual(ulang.state, 'posted')
        # Komponen sekali: satu kali seumur hidup per siswa.
        self._terbitkan(komponen=self.pangkal, periode=False, nominal=1000000)
        with self.assertRaisesRegex(UserError, 'sudah ada'):
            self._terbitkan(komponen=self.pangkal, periode=False, nominal=1000000)

    def test_galat_unik_lain_tidak_disebut_ganda(self):
        """Pelanggaran indeks unik selain indeks tagihan diteruskan apa adanya, bukan "Tagihan ini sudah ada"."""
        Move = self.Move
        self.assertFalse(Move._nti_edu_pesan_ganda('account_move_unique_name', self.siswa_a, self.spp))
        self.assertIn('sudah ada', Move._nti_edu_pesan_ganda(
            'nti_edu_tagihan_unik_periode', self.siswa_a, self.spp))
        lama = self._terbitkan()
        post_asli = type(Move).action_post

        def post_bentrok_nama(moves):
            # Paksa bentrok indeks unik Odoo account_move_unique_name (nama + jurnal entri posted).
            moves.env.cr.execute(
                "UPDATE account_move SET name = %s, state = 'posted' WHERE id IN %s", [lama.name, tuple(moves.ids)])
            return post_asli(moves)

        with patch.object(type(Move), 'action_post', post_bentrok_nama), mute_logger('odoo.sql_db'):
            with self.assertRaises(UniqueViolation):
                self._terbitkan(periode=date(2026, 9, 1))
        self.assertFalse(Move.search([
            ('nti_edu_siswa_id', '=', self.siswa_a.id), ('nti_edu_periode', '=', date(2026, 9, 1))]))

    def test_nol_langsung_lunas(self):
        tagihan = self._terbitkan(potongan=[(self.saudara, 200000)])
        self.assertEqual(tagihan.state, 'posted')
        self.assertEqual(tagihan.amount_total, 0)
        self.assertTrue(tagihan.nti_edu_lunas)

    @freeze_time('2026-09-01')
    def test_api_jembatan(self):
        ekskul = self._buat_komponen('Ekskul Jembatan', 'periode_sekali')
        satu = self.Move._nti_edu_buat_tagihan(self.siswa_a, ekskul, 50000, self.rombel_7a, keterangan='Ekskul Futsal')
        dua = self.Move._nti_edu_buat_tagihan(self.siswa_a, ekskul, 75000, self.rombel_8a)
        self.assertEqual(satu.state, 'posted')
        self.assertEqual(satu.nti_edu_sumber, 'nti_edu.rombel,%s' % self.rombel_7a.id)
        self.assertEqual(satu.invoice_line_ids.name, 'Ekskul Futsal')
        self.assertEqual(satu.invoice_date, date(2026, 9, 1))
        self.assertEqual(satu.invoice_date_due, date(2026, 9, 1) + timedelta(
            days=ekskul.periode_jenis_id.hari_jatuh_tempo))
        self.assertEqual(dua.amount_total, 75000)
        # Tagihan jembatan tidak menghalangi tagihan biasa komponen yang sama.
        self._terbitkan(komponen=ekskul, periode=False, nominal=10000)
        with self.assertRaisesRegex(UserError, 'sudah ada'):
            self.Move._nti_edu_buat_tagihan(self.siswa_a, ekskul, 50000, self.rombel_7a)
        bukan_siswa = self.env['res.partner'].create({'name': 'Bukan Siswa', 'company_id': self.unit_smp.id})
        with self.assertRaises(UserError):
            self.Move._nti_edu_buat_tagihan(bukan_siswa, ekskul, 50000, self.rombel_10a)
        with self.assertRaises(UserError):
            self._terbitkan(siswa=bukan_siswa)

    def test_jurnal_tagihan(self):
        jurnal = self.unit_smp._nti_edu_jurnal_tagihan()
        self.assertEqual(jurnal.type, 'sale')
        self.assertEqual(jurnal.company_id, self.yayasan)
        lain = self.env['account.journal'].create({
            'name': 'Tagihan Sekolah', 'code': 'TGS', 'type': 'sale', 'company_id': self.yayasan.id})
        self.unit_smp.nti_edu_tagihan_jurnal_id = lain
        self.assertEqual(self.unit_smp._nti_edu_jurnal_tagihan(), lain)
        self.assertEqual(self._terbitkan().journal_id, lain)
        with self.assertRaises(ValidationError):
            self.unit_smp.nti_edu_tagihan_jurnal_id = self.env['account.journal'].search([
                ('company_id', '=', self.yayasan.id), ('type', '=', 'bank')], limit=1)

    def test_pengaturan_bawaan(self):
        unit = self.unit_smp
        self.assertEqual(unit.nti_edu_akses_pembukuan, 'dokumen_sekolah')
        self.assertFalse(unit.nti_edu_tagihan_otomatis)
        self.assertFalse(unit.nti_edu_denda_saldo_awal)
        self.assertTrue(unit.nti_edu_email_tagihan_terbit)
        self.assertEqual(unit.nti_edu_pengingat_hari, 3)
        self.assertEqual(unit.nti_edu_pengingat_tunggakan, 0)
        self.assertTrue(unit.nti_edu_denda_hapus_perlu_admin)
        self.assertFalse(unit.nti_edu_wali_kelas_lihat_tunggakan)
        self.assertEqual(unit.nti_edu_bukti_ukuran_maks_mb, 5)

    def test_pengaturan_hanya_admin_sistem(self):
        with self.assertRaises(AccessError):
            self.unit_smp.with_user(self.admin_keu).write({'nti_edu_akses_pembukuan': 'semua'})
        # Admin Data Sekolah punya hak tulis res.company, tetapi bukan untuk pengaturan kebijakan tagihan.
        admin_data = new_test_user(
            self.env, login='tg_admin_data', groups='nti_edu_base.group_base_admin',
            company_id=self.unit_smp.id, company_ids=[(6, 0, self.unit_smp.ids)])
        with self.assertRaises(AccessError):
            self.unit_smp.with_user(admin_data).write({'nti_edu_pengingat_hari': 7})
        self.unit_smp.with_user(admin_data).write({'nti_edu_npsn': '12345678'})
        self.assertEqual(self.unit_smp.nti_edu_npsn, '12345678')
        self.unit_smp.with_user(self.sysadmin).write({'nti_edu_akses_pembukuan': 'semua'})
        self.assertEqual(self.unit_smp.nti_edu_akses_pembukuan, 'semua')
        with self.assertRaises(ValidationError):
            self.unit_smp.with_user(self.sysadmin).write({'nti_edu_tagihan_otomatis': True})
        self.unit_smp.with_user(self.sysadmin).write({
            'nti_edu_tagihan_otomatis': True, 'nti_edu_tagihan_mulai': date(2026, 7, 1)})
        self.assertTrue(self.unit_smp.nti_edu_tagihan_otomatis)

    def test_pengaturan_saat_buat_unit(self):
        """Pembuat company yang bukan Admin Sistem tidak bisa mengisi pengaturan kebijakan selain nilai bawaan."""
        pengelola = new_test_user(
            self.env, login='tg_erp_manager', groups='base.group_erp_manager,base.group_partner_manager',
            company_id=self.yayasan.id, company_ids=[(6, 0, self.yayasan.ids)])
        Company = self.env['res.company'].with_user(pengelola)
        with self.assertRaises(AccessError):
            Company.create({'name': 'Unit Baru Semua', 'nti_edu_akses_pembukuan': 'semua'})
        with self.assertRaises(AccessError):
            Company.create({'name': 'Unit Baru Pengingat', 'nti_edu_pengingat_hari': 9})
        baru = Company.create({
            'name': 'Unit Baru Bawaan', 'nti_edu_akses_pembukuan': 'dokumen_sekolah', 'nti_edu_pengingat_hari': 3,
            'nti_edu_tagihan_otomatis': False})
        self.assertEqual(baru.nti_edu_akses_pembukuan, 'dokumen_sekolah')
        # Admin Sistem tes tidak punya hak kontak; pembuatan company membuat partner.
        self.sysadmin.groups_id = [(4, self.env.ref('base.group_partner_manager').id)]
        sistem = self.env['res.company'].with_user(self.sysadmin).create({
            'name': 'Unit Baru Sistem', 'nti_edu_akses_pembukuan': 'semua'})
        self.assertEqual(sistem.nti_edu_akses_pembukuan, 'semua')

    def test_cek_hak(self):
        Akses = self.env['nti_edu.tagihan.akses']
        grup = 'nti_edu_tagihan.group_tagihan_bendahara'
        Akses.with_user(self.bendahara_smp)._nti_edu_cek_hak(grup, self.unit_smp)
        with self.assertRaises(AccessError):
            Akses.with_user(self.pemantau_smp)._nti_edu_cek_hak(grup, self.unit_smp)
        with self.assertRaises(AccessError):
            Akses.with_user(self.bendahara_sma)._nti_edu_cek_hak(grup, self.unit_smp)
        with self.assertRaises(AccessError):
            Akses.with_user(self.bendahara_smp)._nti_edu_cek_hak(grup, self.unit_smp | self.unit_sma)
        Akses.with_user(self.admin_keu)._nti_edu_cek_hak(grup, self.unit_smp | self.unit_sma)
        Akses.with_user(self.pemantau_smp).sudo()._nti_edu_cek_hak(grup, self.unit_sma)
