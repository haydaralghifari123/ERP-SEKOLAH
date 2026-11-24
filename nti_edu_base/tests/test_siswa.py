# -*- coding: utf-8 -*-
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
