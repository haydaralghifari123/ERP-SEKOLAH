# -*- coding: utf-8 -*-
from lxml import etree

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

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

    def test_tutup_mengosongkan_password(self):
        siswa = self._buat_siswa('Anak Tutup', self.unit_smp, 'T090')
        wizard = self._wizard(siswa)
        wizard.action_buat()
        self.assertTrue(wizard.password_awal)
        self.assertEqual(wizard.action_tutup(), {'type': 'ir.actions.act_window_close'})
        self.assertFalse(wizard.password_awal)
        arch = self.env['nti_edu.akun.portal.wizard'].with_user(self.user_operator_smp).get_view(
            self.env.ref('nti_edu_base.view_akun_portal_wizard_form').id)['arch']
        self.assertTrue(etree.fromstring(arch).xpath('//button[@name="action_tutup"]'))

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

    # --- Putaran perbaikan 1 ---

    def test_wizard_tidak_terbaca_operator_lain(self):
        siswa = self._buat_siswa('Anak Rahasia', self.unit_smp, 'T011')
        wizard = self._wizard(siswa)
        wizard.action_buat()
        operator_sma = self._buat_user('tes_operator_sma2', 'nti_edu_base.group_base_operator', self.unit_sma)
        operator_smp2 = self._buat_user('tes_operator_smp2', 'nti_edu_base.group_base_operator', self.unit_smp)
        for lain in (operator_sma, operator_smp2):
            Wizard = self.env['nti_edu.akun.portal.wizard'].with_user(lain)
            self.assertFalse(Wizard.search([('id', '=', wizard.id)]))
            with self.assertRaises(AccessError):
                Wizard.browse(wizard.id).read(['login', 'password_awal'])

    def test_partner_bukan_siswa_atau_wali_ditolak(self):
        biasa = self.env['res.partner'].create({'name': 'Kontak Biasa', 'email': 'biasa@example.com'})
        with self.assertRaises(UserError):
            self._wizard(biasa).action_buat()
        self.assertFalse(biasa.user_ids)

    def test_wali_unit_lain_ditolak(self):
        siswa_sma = self._buat_siswa('Anak Hanya SMA', self.unit_sma, 'T012')
        wali = self._wali(siswa_sma, email='wali.sma@example.com')
        with self.assertRaises(UserError):
            self._wizard(wali).action_buat()
        self.assertFalse(wali.user_ids)

    def test_partner_arsip_ditolak(self):
        siswa = self._buat_siswa('Anak Arsip', self.unit_smp, 'T013')
        siswa.active = False
        with self.assertRaises(UserError):
            self._wizard(siswa).action_buat()

    def test_siswa_tidak_aktif_ditolak(self):
        siswa = self._buat_siswa('Anak Lulus', self.unit_smp, 'T014', nti_edu_status='lulus')
        with self.assertRaises(UserError):
            self._wizard(siswa).action_buat()
        self.assertFalse(siswa.user_ids)

    def test_wali_banyak_unit_company_ids(self):
        anak_smp = self._buat_siswa('Anak Satu', self.unit_smp, 'T015')
        anak_sma = self._buat_siswa('Anak Dua', self.unit_sma, 'T016')
        wali = self._wali(anak_smp, email='wali.dua@example.com')
        self.env['nti_edu.siswa.wali'].create({'siswa_id': anak_sma.id, 'partner_id': wali.id, 'hubungan': 'ayah'})
        operator_dua = new_test_user(
            self.env, login='tes_operator_dua_ap', groups='nti_edu_base.group_base_operator',
            company_id=self.unit_smp.id, company_ids=[(6, 0, (self.unit_smp | self.unit_sma).ids)])
        self._wizard(wali, user=operator_dua).action_buat()
        user = wali.user_ids
        self.assertEqual(user.company_ids, self.unit_smp | self.unit_sma)
        self.assertEqual(user.company_id, self.unit_smp)

    def test_wali_tautan_lintas_unit_hanya_operator_semua_unit(self):
        anak_smp = self._buat_siswa('Anak SMP W', self.unit_smp, 'T018')
        anak_sma = self._buat_siswa('Anak SMA W', self.unit_sma, 'T019')
        wali = self._wali(anak_smp, email='wali.tautan@example.com')
        self.env['nti_edu.siswa.wali'].create({'siswa_id': anak_sma.id, 'partner_id': wali.id, 'hubungan': 'ibu'})
        operator_sma = self._buat_user('tes_operator_sma_ap', 'nti_edu_base.group_base_operator', self.unit_sma)
        for operator in (operator_sma, self.user_operator_smp):
            with self.assertRaises(AccessError):
                self._wizard(wali, user=operator).action_buat()
        self.assertFalse(wali.user_ids)
        # Tanpa email: kata sandi awal juga tidak boleh muncul bagi operator sebagian unit.
        wali_tanpa = self._wali(anak_smp, phone='0812000111')
        self.env['nti_edu.siswa.wali'].create({'siswa_id': anak_sma.id, 'partner_id': wali_tanpa.id, 'hubungan': 'ibu'})
        wizard = self._wizard(wali_tanpa, user=operator_sma)
        with self.assertRaises(AccessError):
            wizard.action_buat()
        self.assertFalse(wizard.password_awal)
        self.assertFalse(wali_tanpa.user_ids)

    def test_siswa_company_hanya_unit_sendiri(self):
        siswa = self._buat_siswa('Anak Unit', self.unit_smp, 'T017')
        self._wizard(siswa).action_buat()
        self.assertEqual(siswa.user_ids.company_ids, self.unit_smp)
        self.assertEqual(siswa.user_ids.company_id, self.unit_smp)

    def test_login_wizard_tidak_bocorkan_siswa_unit_lain(self):
        sma = self._buat_siswa('Anak SMA Rahasia', self.unit_sma, 'R001', nti_edu_nisn='9988776655')
        wizard = self._wizard(sma)  # operator SMP, siswa SMA
        self.assertFalse(wizard.login)
        self.assertNotIn(wizard.login, ('9988776655', 'smat.R001'))
        with self.assertRaises(AccessError):
            wizard.action_buat()
        self.assertFalse(sma.user_ids)
