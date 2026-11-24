# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import NtiEduCommon


@tagged('post_install', '-at_install')
class TestAkunPortal(NtiEduCommon):

    def _wizard(self, partner, user=None, **vals):
        Wizard = self.env['nti_edu.akun.portal.wizard'].with_user(user or self.user_operator_smp)
        return Wizard.create(dict(vals, partner_id=partner.id))

    def _wali(self, siswa, **vals):
        wali = self.env['res.partner'].create(dict({'name': 'Wali Tes'}, **vals))
        self.env['nti_edu.siswa.wali'].create({'siswa_id': siswa.id, 'partner_id': wali.id, 'hubungan': 'ayah'})
        return wali

    def test_login_nisn_diutamakan(self):
        siswa = self._buat_siswa('Anak NISN', self.unit_smp, 'T001', nti_edu_nisn='0012345678')
        self.assertEqual(siswa._nti_edu_login_default(), '0012345678')
        self.assertEqual(self._wizard(siswa).login, '0012345678')

    def test_login_kode_unit_nis(self):
        smp = self._buat_siswa('Anak SMP', self.unit_smp, 'T001')
        sma = self._buat_siswa('Anak SMA', self.unit_sma, 'T001')
        self.assertEqual(smp._nti_edu_login_default(), 'smpt.T001')
        self.assertEqual(sma._nti_edu_login_default(), 'smat.T001')
        operator_sma = self._buat_user("tes_operator_sma", "nti_edu_base.group_base_operator", self.unit_sma)
        self._wizard(smp).action_buat()
        self._wizard(sma, user=operator_sma).action_buat()
        self.assertEqual(len(smp.user_ids), 1)
        self.assertEqual(len(sma.user_ids), 1)

    def test_login_tanpa_kode_unit_atau_nis(self):
        self.unit_smp.nti_edu_kode = False
        siswa = self._buat_siswa('Anak Tanpa Kode', self.unit_smp, 'T002')
        with self.assertRaises(UserError):
            siswa._nti_edu_login_default()
        wali = self.env['res.partner'].create({'name': 'Wali Kosong'})
        with self.assertRaises(UserError):
            wali._nti_edu_login_default()

    def test_akun_portal_dan_password_awal(self):
        siswa = self._buat_siswa('Anak Portal', self.unit_smp, 'T003')
        wizard = self._wizard(siswa)
        aksi = wizard.action_buat()
        self.assertEqual(aksi['res_id'], wizard.id)
        self.assertEqual(wizard.state, 'selesai')
        user = siswa.user_ids
        self.assertEqual(len(user), 1)
        self.assertTrue(user.share)
        self.assertTrue(user.has_group('base.group_portal'))
        self.assertEqual(user.company_id, self.unit_smp)
        self.assertTrue(wizard.password_awal)

    def test_wali_login_email(self):
        siswa = self._buat_siswa('Anak Wali', self.unit_smp, 'T004')
        wali = self._wali(siswa, email='ayah.tes@example.com')
        wizard = self._wizard(wali)
        self.assertEqual(wizard.login, 'ayah.tes@example.com')
        wizard.action_buat()
        self.assertFalse(wizard.password_awal)
        self.assertEqual(wali.user_ids.login, 'ayah.tes@example.com')
        self.assertEqual(wali.user_ids.company_id, self.unit_smp)

    def test_wali_pegawai_ditolak(self):
        wizard = self._wizard(self.user_guru_smp.partner_id)
        with self.assertRaises(UserError):
            wizard.action_buat()

    def test_sudah_punya_akun_portal_ditolak(self):
        siswa = self._buat_siswa('Anak Dua Kali', self.unit_smp, 'T005')
        self._wizard(siswa).action_buat()
        with self.assertRaises(UserError):
            self._wizard(siswa).action_buat()

    def test_login_bentrok_pesan_jelas(self):
        self.env['res.users'].create({'name': 'Lain', 'login': '0012345678'})
        siswa = self._buat_siswa('Anak Bentrok', self.unit_smp, 'T006', nti_edu_nisn='0012345678')
        with self.assertRaises(UserError) as ctx:
            self._wizard(siswa).action_buat()
        self.assertIn('0012345678', str(ctx.exception))

    def test_hanya_operator(self):
        siswa = self._buat_siswa('Anak Guru', self.unit_smp, 'T007')
        with self.assertRaises(AccessError):
            self._wizard(siswa, user=self.user_guru_smp).action_buat()

    def test_operator_unit_lain_ditolak(self):
        siswa = self._buat_siswa('Anak SMA Lain', self.unit_sma, 'T008')
        with self.assertRaises(AccessError):
            self._wizard(siswa).action_buat()
        self.assertFalse(siswa.user_ids)

    def test_aksi_partner_hanya_operator(self):
        siswa = self._buat_siswa('Anak Aksi', self.unit_smp, 'T009')
        aksi = siswa.with_user(self.user_operator_smp).action_nti_edu_buat_akun_portal()
        self.assertEqual(aksi['res_model'], 'nti_edu.akun.portal.wizard')
        with self.assertRaises(AccessError):
            siswa.with_user(self.user_guru_smp).action_nti_edu_buat_akun_portal()

    def test_eksternal_tidak_melihat_user_portal_siswa(self):
        siswa = self._buat_siswa('Budi Rahasia', self.unit_smp, 'T010')
        self._wizard(siswa).action_buat()
        user = siswa.user_ids
        Users = self.env['res.users'].with_user(self.user_eksternal)
        self.assertFalse(Users.search([('id', '=', user.id)]))
        self.assertFalse(Users.name_search('Budi Rahasia'))
