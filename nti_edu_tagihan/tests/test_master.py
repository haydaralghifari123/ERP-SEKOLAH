# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .common import NtiTagihanCommon


@tagged('post_install', '-at_install')
class TestMaster(NtiTagihanCommon):

    def test_grup(self):
        ref = self.env.ref
        pemantau = ref('nti_edu_tagihan.group_tagihan_pemantau')
        bendahara = ref('nti_edu_tagihan.group_tagihan_bendahara')
        admin = ref('nti_edu_tagihan.group_tagihan_admin')
        self.assertEqual(pemantau.category_id, ref('nti_edu_tagihan.module_category_nti_edu_tagihan'))
        self.assertIn(ref('nti_edu_base.group_base_pengguna'), pemantau.implied_ids)
        self.assertIn(pemantau, bendahara.implied_ids)
        self.assertIn(bendahara, admin.implied_ids)
        self.assertIn(admin, ref('base.group_system').implied_ids)
        self.assertTrue(self.sysadmin.has_group('nti_edu_tagihan.group_tagihan_admin'))
        self.assertFalse(self.bendahara_smp.has_group('nti_edu_tagihan.group_tagihan_admin'))
        akuntansi = ref('account.group_account_invoice') | ref('account.group_account_readonly')
        for grup in pemantau | bendahara | admin:
            self.assertFalse(grup.trans_implied_ids & akuntansi, grup.name)

    def test_data_awal_master(self):
        Bulan = self.env['nti_edu.tagihan.bulan']
        self.assertEqual(Bulan.search_count([]), 12)
        self.assertEqual(self.env.ref('nti_edu_tagihan.bulan_01').nomor, 1)
        self.assertEqual(self.env.ref('nti_edu_tagihan.bulan_12').nomor, 12)
        for xmlid in ('periode_bulanan', 'periode_semester', 'periode_tahunan', 'periode_sekali'):
            self.assertTrue(self.env.ref('nti_edu_tagihan.%s' % xmlid).active)
        self.assertEqual(self.env.ref('nti_edu_tagihan.periode_bulanan').dasar, 'bulan')
        self.assertEqual(self.env.ref('nti_edu_tagihan.periode_sekali').dasar, 'sekali')
        masuk = self.env.ref('nti_edu_tagihan.aturan_masuk_penuh') \
            | self.env.ref('nti_edu_tagihan.aturan_masuk_berikutnya') \
            | self.env.ref('nti_edu_tagihan.aturan_masuk_prorata')
        self.assertEqual(sorted(masuk.mapped('cara')), ['berikutnya', 'penuh', 'prorata'])
        lainnya = self.env['nti_edu.tagihan.alasan.tolak'].search([('name', '=', 'Lainnya')])
        self.assertEqual(len(lainnya), 1)
        self.assertTrue(lainnya.perlu_catatan)
        denda = self.env.ref('nti_edu_tagihan.aturan_denda_contoh')
        self.assertEqual((denda.tipe, denda.nilai, denda.berulang, denda.tenggang_hari),
                         ('tetap', 10000, 'per_bulan', 7))
        self.assertEqual(denda.komponen_denda_id, self.env.ref('nti_edu_tagihan.komponen_denda'))
        self.assertEqual(self.env.ref('nti_edu_tagihan.komponen_denda').jenis, 'denda')
        self.assertEqual(self.env.ref('nti_edu_tagihan.aturan_cicilan_4_bulanan').maks_kali, 4)
        self.assertEqual(self.env.ref('nti_edu_tagihan.aturan_cicilan_2_per_6_bulan').jarak, 6)

    def test_komponen_buat_produk(self):
        komponen = self._buat_komponen('SPP Tes', 'periode_bulanan', kode='SPPT')
        self.assertEqual(komponen.aturan_masuk_id, self.env.ref('nti_edu_tagihan.aturan_masuk_penuh'))
        produk = komponen.product_id
        self.assertTrue(produk)
        self.assertEqual(produk.type, 'service')
        self.assertEqual(produk.name, 'SPP Tes')
        self.assertFalse(produk.taxes_id)

        komponen.name = 'SPP Bulanan Tes'
        self.assertEqual(produk.name, 'SPP Bulanan Tes')
        komponen.company_id = self.unit_smp
        self.assertEqual(produk.company_id, self.unit_smp)
        komponen.company_id = False

        akun = self.env['account.account'].search([
            ('company_ids', 'in', self.yayasan.id), ('account_type', '=', 'income')], limit=1)
        self.assertTrue(akun)
        komponen.akun_pendapatan_id = akun
        self.assertEqual(produk.with_company(self.yayasan).property_account_income_id, akun)
        # Tagihan terbit di unit (cabang yayasan): akun pendapatan berlaku juga di sana.
        self.assertEqual(produk.with_company(self.unit_smp).property_account_income_id, akun)

        # Komponen dibuat dengan akun langsung.
        lain = self._buat_komponen('Kegiatan Tes', 'periode_semester', akun_pendapatan_id=akun.id)
        self.assertEqual(lain.product_id.with_company(self.unit_sma).property_account_income_id, akun)

    def test_komponen_biaya_wajib_periode(self):
        with self.assertRaises(ValidationError):
            self._buat_komponen('Tanpa Periode', None, jenis='biaya')
        denda = self._buat_komponen('Denda Tes', None, jenis='denda')
        self.assertEqual(denda.jenis, 'denda')

    def test_validasi_master(self):
        with self.assertRaises(ValidationError):
            self.env['nti_edu.tagihan.periode.jenis'].create(
                {'name': 'Nol Bulan', 'dasar': 'bulan', 'jumlah_bulan': 0})
        with self.assertRaises(ValidationError):
            self.env['nti_edu.tagihan.periode.jenis'].create(
                {'name': 'Terbit 31', 'dasar': 'bulan', 'hari_terbit': 31})
        Cicilan = self.env['nti_edu.tagihan.aturan.cicilan']
        with self.assertRaises(ValidationError):
            Cicilan.create({'name': 'Sekali', 'maks_kali': 1, 'jarak': 1, 'jarak_satuan': 'bulan'})
        with self.assertRaises(ValidationError):
            Cicilan.create({'name': 'Lunas di Muka', 'maks_kali': 2, 'jarak': 1, 'jarak_satuan': 'bulan',
                            'uang_muka_persen': 100})
        with self.assertRaises(ValidationError):
            self.env['nti_edu.tagihan.aturan.denda'].create({
                'name': 'Denda Biaya', 'tipe': 'tetap', 'nilai': 5000, 'berulang': 'sekali',
                'komponen_denda_id': self._buat_komponen('Bukan Denda', 'periode_bulanan').id})

    def test_hak_master(self):
        komponen = self._buat_komponen('SPP Hak', 'periode_bulanan')
        Komponen = self.env['nti_edu.tagihan.komponen']
        self.assertIn(komponen, Komponen.with_user(self.bendahara_smp).search([]))
        aturan = self.env.ref('nti_edu_tagihan.aturan_denda_contoh')
        self.assertIn(aturan, self.env['nti_edu.tagihan.aturan.denda'].with_user(self.bendahara_smp).search([]))
        self.assertIn(komponen, Komponen.with_user(self.pemantau_smp).search([]))
        periode = self.env.ref('nti_edu_tagihan.periode_bulanan').id
        with self.assertRaises(AccessError):
            Komponen.with_user(self.bendahara_smp).create({'name': 'SPP Bendahara', 'periode_jenis_id': periode})
        with self.assertRaises(AccessError):
            self.env['nti_edu.tagihan.aturan.cicilan'].with_user(self.bendahara_smp).create(
                {'name': 'Cicil Bendahara', 'maks_kali': 2, 'jarak': 1, 'jarak_satuan': 'bulan'})
        with self.assertRaises(AccessError):
            komponen.with_user(self.bendahara_smp).write({'name': 'Diubah Bendahara'})

        baru = Komponen.with_user(self.admin_keu).create({'name': 'SPP Admin', 'periode_jenis_id': periode})
        self.assertTrue(baru.sudo().product_id)
        self.env['nti_edu.tagihan.aturan.cicilan'].with_user(self.admin_keu).create(
            {'name': 'Cicil Admin', 'maks_kali': 3, 'jarak': 1, 'jarak_satuan': 'bulan'})

    def test_admin_keu_akun_pendapatan(self):
        # Admin Keuangan bukan akuntan: memilih dan membaca akun pendapatan tanpa AccessError.
        akun = self.env['account.account'].search([
            ('company_ids', 'in', self.yayasan.id), ('account_type', '=', 'income')], limit=1)
        Akun = self.env['account.account'].with_user(self.admin_keu)
        hasil = Akun.name_search(akun.code, args=[('account_type', 'in', ('income', 'income_other'))])
        self.assertIn(akun.id, [r[0] for r in hasil])
        komponen = self.env['nti_edu.tagihan.komponen'].with_user(self.admin_keu).create({
            'name': 'SPP Akun Admin', 'periode_jenis_id': self.env.ref('nti_edu_tagihan.periode_bulanan').id,
            'akun_pendapatan_id': akun.id})
        self.assertEqual(komponen.akun_pendapatan_id, akun)
        self.assertIn(akun.sudo().name, komponen.akun_pendapatan_id.display_name)
        akun_lain = Akun.search([('account_type', '=', 'income_other')], limit=1) or akun
        komponen.write({'akun_pendapatan_id': akun_lain.id})
        komponen.invalidate_recordset()
        self.assertEqual(komponen.read(['akun_pendapatan_id'])[0]['akun_pendapatan_id'][0], akun_lain.id)
        self.assertEqual(komponen.sudo().product_id.with_company(self.unit_smp).property_account_income_id,
                         akun_lain)

    def test_aturan_multi_unit(self):
        komponen_sma = self._buat_komponen('SPP SMA Saja', 'periode_bulanan', company_id=self.unit_sma.id)
        komponen_umum = self._buat_komponen('SPP Semua Unit', 'periode_bulanan')
        alasan_sma = self.env['nti_edu.tagihan.alasan.tolak'].create(
            {'name': 'Alasan SMA Saja', 'company_id': self.unit_sma.id})
        alasan_umum = self.env['nti_edu.tagihan.alasan.tolak'].create({'name': 'Alasan Semua Unit'})
        for model, khusus, umum in (('nti_edu.tagihan.komponen', komponen_sma, komponen_umum),
                                    ('nti_edu.tagihan.alasan.tolak', alasan_sma, alasan_umum)):
            lihat_smp = self.env[model].with_user(self.bendahara_smp).search([])
            lihat_sma = self.env[model].with_user(self.bendahara_sma).search([])
            self.assertNotIn(khusus, lihat_smp, model)
            self.assertIn(khusus, lihat_sma, model)
            self.assertIn(umum, lihat_smp, model)
            self.assertIn(umum, lihat_sma, model)
        with self.assertRaises(AccessError):
            komponen_sma.with_user(self.bendahara_smp).read(['name'])

    def test_rekening_untuk_unit(self):
        jurnal = self.env['account.journal'].search([
            ('company_id', '=', self.yayasan.id), ('type', '=', 'bank')], limit=1)
        semua = self.env['nti_edu.tagihan.rekening'].create({
            'name': 'Rekening Semua Unit', 'bank': 'Bank Tes', 'nomor': '111', 'atas_nama': 'Yayasan Tes',
            'journal_id': jurnal.id})
        khusus_sma = self._buat_rekening(self.unit_sma)
        Rekening = self.env['nti_edu.tagihan.rekening']
        untuk_smp = Rekening._untuk_unit(self.unit_smp)
        self.assertIn(semua, untuk_smp)
        self.assertNotIn(khusus_sma, untuk_smp)
        self.assertIn(khusus_sma, Rekening._untuk_unit(self.unit_sma))
        semua.active = False
        self.assertNotIn(semua, Rekening._untuk_unit(self.unit_smp))
        jurnal_jual = self.env['account.journal'].search([
            ('company_id', '=', self.yayasan.id), ('type', '=', 'sale')], limit=1)
        with self.assertRaises(ValidationError):
            khusus_sma.journal_id = jurnal_jual
        # Jurnal milik unit lain tidak bisa dipakai rekening SMA.
        jurnal_smp = self.env['account.journal'].create({
            'name': 'Bank SMP Tes', 'code': 'BSMPT', 'type': 'bank', 'company_id': self.unit_smp.id})
        with self.assertRaises(ValidationError):
            khusus_sma.journal_id = jurnal_smp

    def test_rekening_akun_penampung(self):
        """Rekening hanya boleh memakai jurnal yang payment-nya pasti punya entri jurnal (akun penampung)."""
        jurnal = self.env['account.journal'].search([
            ('company_id', '=', self.yayasan.id), ('type', '=', 'bank')], limit=1)
        metode = jurnal.inbound_payment_method_line_ids
        akun = self.env['account.chart.template'].with_company(self.yayasan).ref(
            'account_journal_payment_debit_account_id')
        metode.write({'payment_account_id': False})
        Rekening = self.env['nti_edu.tagihan.rekening']
        vals = {'name': 'Rekening Penampung', 'bank': 'Bank Tes', 'nomor': '222', 'atas_nama': 'Yayasan Tes',
                'journal_id': jurnal.id}
        # Community: Odoo memakai akun "Outstanding Receipts" bagan akun sebagai cadangan.
        rekening = Rekening.create(vals)
        self.assertEqual(rekening._nti_edu_akun_penampung(), akun)
        # Mode Accountant ("in_payment"): tanpa cadangan, metode tanpa akun penampung ditolak.
        self.patch(type(self.env['account.move']), '_get_invoice_in_payment_state', lambda self: 'in_payment')
        with self.assertRaises(ValidationError) as galat:
            Rekening.create(dict(vals, name='Rekening Kedua'))
        self.assertIn('akun penampung', str(galat.exception))
        with self.assertRaises(ValidationError) as galat:
            rekening.company_ids = self.unit_smp
        self.assertIn('akun penampung', str(galat.exception))
        metode[:1].payment_account_id = akun
        self.assertEqual(rekening._nti_edu_metode_masuk(), metode[:1])
        Rekening.create(dict(vals, name='Rekening Ketiga'))
        # Jurnal tanpa metode pembayaran masuk ditolak.
        jurnal_kosong = self.env['account.journal'].create({
            'name': 'Bank Kosong Tes', 'code': 'BKOST', 'type': 'bank', 'company_id': self.yayasan.id})
        jurnal_kosong.inbound_payment_method_line_ids.unlink()
        with self.assertRaises(ValidationError) as galat:
            Rekening.create(dict(vals, name='Rekening Keempat', journal_id=jurnal_kosong.id))
        self.assertIn('metode pembayaran masuk', str(galat.exception))
