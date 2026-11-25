# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .common import NtiPegawaiCommon


@tagged('post_install', '-at_install')
class TestPenjaga(NtiPegawaiCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.budi_smp = cls._buat_pegawai('Budi', cls.unit_smp)
        cls.budi_sma = cls._buat_pegawai(
            'Budi', cls.unit_sma, work_contact_id=cls.budi_smp.work_contact_id.id)
        cls.sari = cls._buat_pegawai('Sari', cls.unit_smp)
        cls.siti_sma = cls._buat_pegawai('Siti', cls.unit_sma)

    def _sebagai(self, rec, user):
        return rec.with_user(user).with_context(allowed_company_ids=user.company_ids.ids)

    def test_tu_dua_unit_ubah_profil_terlihat_di_keduanya(self):
        self._sebagai(self.budi_sma, self.tu_dua).nti_edu_nuptk = '1234567890'
        self.assertEqual(self._sebagai(self.budi_smp, self.tu_dua).nti_edu_nuptk, '1234567890')
        self.assertEqual(self.budi_smp.work_contact_id.nti_edu_nuptk, '1234567890')

    def test_tu_satu_unit_ditolak(self):
        with self.assertRaises(AccessError):
            self._sebagai(self.budi_sma, self.tu_sma).nti_edu_nuptk = '999'
        self.assertFalse(self.budi_smp.work_contact_id.nti_edu_nuptk)
        kontak = self.budi_smp.work_contact_id
        with self.assertRaises(AccessError):
            self._sebagai(kontak, self.tu_sma).write({'nti_edu_nuptk': '999'})
        self.assertFalse(kontak.nti_edu_nuptk)
        Sert = self.env['nti_edu.pegawai.sertifikasi']
        with self.assertRaises(AccessError):
            self._sebagai(Sert, self.tu_sma).create({'partner_id': kontak.id, 'nomor': 'A'})
        sert = Sert.create({'partner_id': kontak.id, 'nomor': 'B'})
        with self.assertRaises(AccessError):
            self._sebagai(sert, self.tu_sma).write({'nomor': 'C'})
        self.assertEqual(sert.nomor, 'B')

    def test_tu_satu_unit_boleh_untuk_pegawai_unitnya(self):
        sari = self._sebagai(self.sari, self.tu_smp)
        sari.nti_edu_nuptk = '555'
        sari.nti_edu_status_kepegawaian = 'gty'
        self.assertEqual(self.sari.work_contact_id.nti_edu_nuptk, '555')
        self.assertEqual(self.sari.work_contact_id.nti_edu_status_kepegawaian, 'gty')
        sert = self._sebagai(self.env['nti_edu.pegawai.sertifikasi'], self.tu_smp).create(
            {'partner_id': self.sari.work_contact_id.id, 'nomor': 'S1'})
        sert.write({'nomor': 'S2'})
        self.assertEqual(sert.nomor, 'S2')

    def test_nik_satu_per_orang(self):
        self._sebagai(self.budi_smp, self.tu_dua).nti_edu_nik = '3201000000000001'
        self.assertEqual(self.budi_smp.work_contact_id.nti_edu_nik, '3201000000000001')
        self.assertEqual(self._sebagai(self.budi_sma, self.tu_dua).nti_edu_nik, '3201000000000001')
        with self.assertRaises(AccessError):
            self._sebagai(self.budi_sma, self.tu_sma).nti_edu_nik = '1'

    def test_tu_tidak_isi_user_id(self):
        user = self.guru_smp
        with self.assertRaises(AccessError):
            self._sebagai(self.sari, self.tu_smp).write({'user_id': user.id})
        self.assertFalse(self.sari.user_id)
        self._sebagai(self.sari, self.hrd).write({'user_id': user.id})
        self.assertEqual(self.sari.user_id, user)

    def test_hapus_hanya_hrd(self):
        sert = self.env['nti_edu.pegawai.sertifikasi'].create(
            {'partner_id': self.sari.work_contact_id.id, 'nomor': 'X'})
        with self.assertRaises(AccessError):
            self._sebagai(sert, self.tu_smp).unlink()
        with self.assertRaises(AccessError):
            self._sebagai(self.sari, self.tu_smp).unlink()
        self.assertTrue(sert.exists() and self.sari.exists())
        self._sebagai(sert, self.hrd).unlink()
        self._sebagai(self.sari, self.hrd).unlink()
        self.assertFalse(sert.exists() or self.sari.exists())

    def test_sertifikasi_unit_lain_tak_terbaca(self):
        sert = self.env['nti_edu.pegawai.sertifikasi'].create(
            {'partner_id': self.siti_sma.work_contact_id.id, 'nomor': 'Z'})
        Sert = self._sebagai(self.env['nti_edu.pegawai.sertifikasi'], self.tu_smp)
        self.assertFalse(Sert.search([('id', '=', sert.id)]))
        with self.assertRaises(AccessError):
            self._sebagai(sert, self.tu_smp).nomor
        self.assertEqual(self._sebagai(sert, self.hrd).nomor, 'Z')

    def test_nuptk_dirapikan(self):
        a = self.budi_smp.work_contact_id
        a.write({'nti_edu_nuptk': ' 123 '})
        self.assertEqual(a.nti_edu_nuptk, '123')
        with self.assertRaises(ValidationError):
            self.sari.work_contact_id.write({'nti_edu_nuptk': '123'})
        a.write({'nti_edu_nip': '   '})
        self.assertFalse(a.nti_edu_nip)

    def test_nik_partner_pegawai_dijaga(self):
        grup = 'nti_edu_base.group_base_operator,nti_edu_pegawai.group_pegawai_operator'
        op_sma = self._buat_user('peg_op_sma', grup, self.unit_sma)
        op_dua = self._buat_user('peg_op_dua', grup, self.unit_smp | self.unit_sma)
        kontak = self.budi_smp.work_contact_id
        kontak.company_id = False  # agar aturan rekaman multi-unit kontak tidak menolak lebih dulu
        with self.assertRaisesRegex(AccessError, "Profil kepegawaian"):
            self._sebagai(kontak, op_sma).write({'nti_edu_nik': '3201000000000009'})
        self.assertFalse(kontak.nti_edu_nik)
        self._sebagai(kontak, op_dua).write({'nti_edu_nik': '3201000000000009'})
        self.assertEqual(kontak.nti_edu_nik, '3201000000000009')

    def test_tu_tak_bisa_tautkan_kontak_pegawai_unit_lain(self):
        kontak_sma = self.siti_sma.work_contact_id
        Emp = self._sebagai(self.env['hr.employee'], self.tu_smp)
        with self.assertRaises(AccessError):
            Emp.create({'name': 'Siti', 'company_id': self.unit_smp.id, 'work_contact_id': kontak_sma.id})
        with self.assertRaises(AccessError):
            self._sebagai(self.sari, self.tu_smp).write({'work_contact_id': kontak_sma.id})
        self.assertNotEqual(self.sari.work_contact_id, kontak_sma)

    def test_tu_dua_unit_boleh_tautkan(self):
        kontak_sma = self.siti_sma.work_contact_id
        for user in (self.tu_dua, self.hrd):
            emp = self._sebagai(self.env['hr.employee'], user).create(
                {'name': 'Siti', 'company_id': self.unit_smp.id, 'work_contact_id': kontak_sma.id})
            self.assertEqual(emp.work_contact_id, kontak_sma)
            emp.sudo().unlink()
