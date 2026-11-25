# -*- coding: utf-8 -*-
from datetime import date

from lxml import etree

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import new_test_user, tagged

from .common import NtiEduCommon


@tagged('post_install', '-at_install')
class TestSiswa(NtiEduCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_pm = new_test_user(
            cls.env, login='tes_pengguna_pm',
            groups='nti_edu_base.group_base_pengguna,base.group_partner_manager',
            company_id=cls.unit_smp.id, company_ids=[(6, 0, cls.unit_smp.ids)])

    # --- Kunci kontak wali ---

    def _wali_dengan_anak_smp(self):
        siswa = self._buat_siswa('Anak Kontak', self.unit_smp, 'KW01')
        wali = self.env['res.partner'].create({'name': 'Wali Kontak', 'email': 'lama@contoh.id'})
        self.env['nti_edu.siswa.wali'].create(
            {'siswa_id': siswa.id, 'partner_id': wali.id, 'hubungan': 'ayah'})
        return wali

    def _operator_sma(self):
        return self._buat_user('tes_operator_sma_kw', 'nti_edu_base.group_base_operator', self.unit_sma)

    def test_operator_unit_anak_ubah_email_wali(self):
        wali = self._wali_dengan_anak_smp()
        wali.with_user(self.user_operator_smp).write({'email': 'baru@contoh.id'})
        self.assertEqual(wali.email, 'baru@contoh.id')

    def test_operator_unit_lain_tidak_ubah_email_wali(self):
        wali = self._wali_dengan_anak_smp()
        operator_sma = self._operator_sma()
        for nama in ('email', 'phone', 'mobile'):
            with self.assertRaises(AccessError):
                wali.with_user(operator_sma).write({nama: 'x@contoh.id' if nama == 'email' else '0812'})
        self.assertEqual(wali.email, 'lama@contoh.id')
        self.assertFalse(wali.phone)
        self.assertFalse(wali.mobile)

    def test_tautan_wali_lintas_unit_tidak_beri_hak_kontak(self):
        wali = self._wali_dengan_anak_smp()
        operator_sma = self._operator_sma()
        anak_sma = self._buat_siswa('Anak SMA KW', self.unit_sma, 'KW02')
        self.env['nti_edu.siswa.wali'].create(
            {'siswa_id': anak_sma.id, 'partner_id': wali.id, 'hubungan': 'ibu'})
        # Wali kini beranak di SMP dan SMA: operator satu unit saja tidak cukup.
        for operator in (operator_sma, self.user_operator_smp):
            for nama in ('email', 'phone', 'mobile'):
                with self.assertRaises(AccessError):
                    wali.with_user(operator).write({nama: 'x@contoh.id' if nama == 'email' else '0812'})
        self.assertEqual(wali.email, 'lama@contoh.id')
        dua_unit = new_test_user(
            self.env, login='tes_operator_dua_kw', groups='nti_edu_base.group_base_operator',
            company_id=self.unit_smp.id, company_ids=[(6, 0, (self.unit_smp | self.unit_sma).ids)])
        wali.with_user(dua_unit).write({'email': 'resmi@contoh.id'})
        self.assertEqual(wali.email, 'resmi@contoh.id')

    def test_pengelola_kontak_non_sekolah_tidak_ubah_email_wali(self):
        wali = self._wali_dengan_anak_smp()
        pm = new_test_user(
            self.env, login='tes_pm_saja_kw', groups='base.group_user,base.group_partner_manager',
            company_id=self.unit_smp.id, company_ids=[(6, 0, self.unit_smp.ids)])
        with self.assertRaises(AccessError):
            wali.with_user(pm).write({'email': 'curang@contoh.id'})
        self.assertEqual(wali.email, 'lama@contoh.id')

    def test_wali_ubah_kontak_sendiri(self):
        wali = self._wali_dengan_anak_smp()
        akun = self.env['res.users'].create({
            'name': wali.name, 'login': 'wali_kw', 'partner_id': wali.id,
            'groups_id': [(6, 0, self.env.ref('base.group_portal').ids)]})
        akun.with_user(akun).write({'email': 'sendiri@contoh.id'})
        self.assertEqual(wali.email, 'sendiri@contoh.id')
        # Jalur guard langsung: partner sendiri dinilai boleh.
        self.assertTrue(wali.with_user(akun)._nti_edu_boleh_ubah_kontak_wali())

    def test_field_lain_wali_tetap_bebas(self):
        wali = self._wali_dengan_anak_smp()
        wali.with_user(self._operator_sma()).write({'comment': 'catatan'})
        self.assertIn('catatan', wali.comment)

    def test_nis_unik_per_unit(self):
        self._buat_siswa('A', self.unit_smp, 'T001')
        with self.assertRaises(ValidationError):
            self._buat_siswa('B', self.unit_smp, 'T001')
        self._buat_siswa('C', self.unit_sma, 'T001')

    def test_nis_unik_termasuk_arsip(self):
        a = self._buat_siswa('A', self.unit_smp, 'T001')
        a.active = False
        with self.assertRaises(ValidationError):
            self._buat_siswa('B', self.unit_smp, 'T001')

    def test_nisn_unik_global(self):
        self._buat_siswa('A', self.unit_smp, 'T001', nti_edu_nisn='0012345678')
        with self.assertRaises(ValidationError):
            self._buat_siswa('B', self.unit_sma, 'T002', nti_edu_nisn='0012345678')
        self._buat_siswa('C', self.unit_smp, 'T003')
        self._buat_siswa('D', self.unit_smp, 'T004')

    def test_siswa_wajib_unit(self):
        with self.assertRaises(ValidationError):
            self.env['res.partner'].create({'name': 'Tanpa Unit', 'nti_edu_is_siswa': True})

    def test_siswa_di_yayasan_ditolak(self):
        with self.assertRaises(ValidationError):
            self._buat_siswa('X', self.yayasan, 'Y001')

    def test_siswa_sekolah_mandiri_boleh(self):
        mandiri = self.env['res.company'].create({'name': 'Sekolah Mandiri', 'nti_edu_jenis': 'unit'})
        self.assertFalse(mandiri.parent_id)
        siswa = self._buat_siswa('Anak Mandiri', mandiri, 'M001')
        self.assertEqual(siswa.company_id, mandiri)

    def test_form_siswa_domain_unit(self):
        arch = self.env['res.partner'].get_views(
            [(self.env.ref('nti_edu_base.view_siswa_form').id, 'form')])['views']['form']['arch']
        field = etree.fromstring(arch).xpath('//field[@name="company_id"]')[0]
        self.assertIn('nti_edu_jenis', field.get('domain', ''))

    def test_wali_ditandai(self):
        siswa = self._buat_siswa('A', self.unit_smp, 'T001')
        wali = self.env['res.partner'].create({'name': 'Ayah A'})
        self.assertFalse(wali.nti_edu_is_wali)
        baris = self.env['nti_edu.siswa.wali'].create(
            {'siswa_id': siswa.id, 'partner_id': wali.id, 'hubungan': 'ayah'})
        self.assertTrue(wali.nti_edu_is_wali)
        baris.unlink()
        self.assertFalse(wali.nti_edu_is_wali)

    def test_wali_tanpa_unit(self):
        siswa = self._buat_siswa('A', self.unit_smp, 'T001')
        wali = self.env['res.partner'].create({'name': 'Ibu A', 'company_id': self.unit_smp.id})
        self.env['nti_edu.siswa.wali'].create(
            {'siswa_id': siswa.id, 'partner_id': wali.id, 'hubungan': 'ibu'})
        self.assertFalse(wali.company_id)
        self.assertEqual(wali.with_user(self.user_guru_sma).name, 'Ibu A')

    def test_guru_tidak_baca_nik(self):
        siswa = self._buat_siswa('A', self.unit_smp, 'T001', nti_edu_nik='3201000000000001')
        with self.assertRaises(AccessError):
            siswa.with_user(self.user_guru_smp).read(['nti_edu_nik'])
        data = siswa.with_user(self.user_operator_smp).read(['nti_edu_nik'])
        self.assertEqual(data[0]['nti_edu_nik'], '3201000000000001')

    def test_guru_tidak_bisa_ubah_siswa(self):
        siswa = self._buat_siswa('A', self.unit_smp, 'T001')
        with self.assertRaises(AccessError):
            siswa.with_user(self.user_pm).write({'name': 'X'})
        biasa = self.env['res.partner'].create({'name': 'Biasa', 'company_id': self.unit_smp.id})
        biasa.with_user(self.user_pm).write({'name': 'X'})
        self.assertEqual(biasa.name, 'X')

    def test_guru_tidak_bisa_ubah_siswa_campuran(self):
        siswa = self._buat_siswa('A', self.unit_smp, 'T001')
        biasa = self.env['res.partner'].create({'name': 'Biasa', 'company_id': self.unit_smp.id})
        with self.assertRaises(AccessError):
            (biasa | siswa).with_user(self.user_pm).write({'name': 'X'})

    def test_non_operator_tidak_bisa_jadikan_siswa(self):
        biasa = self.env['res.partner'].create({'name': 'Biasa', 'company_id': self.unit_smp.id})
        with self.assertRaises(AccessError):
            biasa.with_user(self.user_pm).write({'nti_edu_is_siswa': True})

    def test_arsip_siswa_menutup_keanggotaan(self):
        tahun = self.env['nti_edu.tahun.ajaran'].create({
            'name': '2026/2027', 'tanggal_mulai': date(2026, 7, 13), 'tanggal_selesai': date(2027, 6, 30)})
        rombel = self.env['nti_edu.rombel'].create({
            'name': 'VIII A', 'tahun_ajaran_id': tahun.id, 'company_id': self.unit_smp.id,
            'tingkat_id': self.env.ref('nti_edu_base.tingkat_smp_8').id})
        siswa = self._buat_siswa('Arsip', self.unit_smp, 'T050')
        anggota = self.env['nti_edu.rombel.anggota'].create({'rombel_id': rombel.id, 'siswa_id': siswa.id})
        self.assertEqual(rombel.jumlah_siswa, 1)
        siswa.with_user(self.user_operator_smp).write({'active': False})
        self.assertTrue(anggota.tanggal_keluar)
        self.assertEqual(rombel.jumlah_siswa, 0)

    def test_operator_bisa_ubah_siswa(self):
        siswa = self._buat_siswa('A', self.unit_smp, 'T001')
        siswa.with_user(self.user_operator_smp).write({'nti_edu_nis': 'T009'})
        self.assertEqual(siswa.nti_edu_nis, 'T009')

    def test_buat_siswa_oleh_non_operator_ditolak(self):
        Partner = self.env['res.partner'].with_user(self.user_pm)
        with self.assertRaises(AccessError):
            Partner.create({'name': 'Baru', 'nti_edu_is_siswa': True, 'company_id': self.unit_smp.id})
        with self.assertRaises(AccessError):
            Partner.with_context(default_nti_edu_is_siswa=True).create(
                {'name': 'Baru', 'company_id': self.unit_smp.id})

    def test_hapus_siswa_oleh_non_operator_ditolak(self):
        siswa = self._buat_siswa('A', self.unit_smp, 'T001')
        with self.assertRaises(AccessError):
            siswa.with_user(self.user_pm).unlink()

    def test_guru_tidak_bisa_ubah_kontak_siswa(self):
        siswa = self._buat_siswa('A', self.unit_smp, 'T001')
        biasa = self.env['res.partner'].create({'name': 'Biasa', 'company_id': self.unit_smp.id})
        negara = self.env.ref('base.id')
        for vals in (
            {'email': 'x@contoh.id'}, {'phone': '0812'}, {'street': 'Jl. X'}, {'street2': 'Y'},
            {'zip': '40000'}, {'city': 'Bandung'}, {'country_id': negara.id}, {'state_id': False},
            {'image_1920': False}, {'active': False},
        ):
            with self.assertRaises(AccessError, msg=str(vals)):
                siswa.with_user(self.user_pm).write(vals)
        biasa.with_user(self.user_pm).write({'email': 'x@contoh.id', 'phone': '0812', 'street': 'Jl. X'})
        biasa.with_user(self.user_pm).write({'active': False})
        self.assertFalse(biasa.active)
        siswa.with_user(self.user_operator_smp).write({'email': 'o@contoh.id'})
        self.assertEqual(siswa.email, 'o@contoh.id')

    def test_wali_partner_unit_lain_ditolak(self):
        siswa = self._buat_siswa('A', self.unit_smp, 'T001')
        asing = self.env['res.partner'].create({'name': 'Vendor SMA', 'company_id': self.unit_sma.id})
        with self.assertRaises(AccessError):
            self.env['nti_edu.siswa.wali'].with_user(self.user_operator_smp).create(
                {'siswa_id': siswa.id, 'partner_id': asing.id, 'hubungan': 'wali'})
        self.assertEqual(asing.company_id, self.unit_sma)

    def test_acl_wali_hanya_operator_menulis(self):
        akses = self.env['ir.model.access'].sudo().search([('model_id.model', '=', 'nti_edu.siswa.wali')])
        for a in akses.filtered(lambda x: x.perm_create or x.perm_write or x.perm_unlink):
            self.assertEqual(a.group_id, self.env.ref('nti_edu_base.group_base_operator'))

    def test_wali_baris_hanya_operator_dan_per_unit(self):
        siswa_smp = self._buat_siswa('A', self.unit_smp, 'T001')
        siswa_sma = self._buat_siswa('B', self.unit_sma, 'T002')
        wali = self.env['res.partner'].create({'name': 'Wali X'})
        Baris = self.env['nti_edu.siswa.wali']
        b_smp = Baris.create({'siswa_id': siswa_smp.id, 'partner_id': wali.id, 'hubungan': 'ibu'})
        b_sma = Baris.create({'siswa_id': siswa_sma.id, 'partner_id': wali.id, 'hubungan': 'ibu'})
        with self.assertRaises(AccessError):
            Baris.with_user(self.user_guru_sma).search([])
        terlihat = Baris.with_user(self.user_operator_smp).search([])
        self.assertIn(b_smp, terlihat)
        self.assertNotIn(b_sma, terlihat)

    def test_guru_tidak_bisa_pindah_alamat_via_parent(self):
        siswa = self._buat_siswa('A', self.unit_smp, 'T001', street='Jl. Asli')
        lain = self.env['res.partner'].create(
            {'name': 'Lain', 'company_id': self.unit_smp.id, 'street': 'Jl. Lain', 'is_company': True})
        with self.assertRaises(AccessError):
            siswa.with_user(self.user_pm).write({'parent_id': lain.id})
        with self.assertRaises(AccessError):
            siswa.with_user(self.user_pm).update_address({'street': 'Jl. Suntik'})
        self.assertEqual(siswa.street, 'Jl. Asli')

    def test_guru_tidak_bisa_suntik_alamat_via_kontak_anak(self):
        siswa = self._buat_siswa('A', self.unit_smp, 'T001')
        with self.assertRaises(AccessError):
            self.env['res.partner'].with_user(self.user_pm).create(
                {'name': 'Anak Kontak', 'parent_id': siswa.id, 'street': 'Jl. Suntik',
                 'company_id': self.unit_smp.id})
        self.assertFalse(siswa.street)
        # Operator boleh.
        self.env['res.partner'].with_user(self.user_operator_smp).create(
            {'name': 'Anak Kontak', 'parent_id': siswa.id, 'street': 'Jl. Sah',
             'company_id': self.unit_smp.id})
        self.assertEqual(siswa.street, 'Jl. Sah')

    def test_duplikat_tidak_menyalin_identitas(self):
        siswa = self._buat_siswa('Asli', self.unit_smp, 'D001', nti_edu_nisn='1234567890', nti_edu_nik='3171')
        salinan = siswa.copy()
        self.assertFalse(salinan.nti_edu_nis)
        self.assertFalse(salinan.nti_edu_nisn)
        self.assertFalse(salinan.nti_edu_nik)
