# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import NtiPegawaiCommon


@tagged('post_install', '-at_install')
class TestAkunLogin(NtiPegawaiCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.smp = cls._buat_pegawai('Bu Dua Unit', cls.unit_smp, work_email='budua@contoh.id')
        cls.sma = cls._buat_pegawai(
            'Bu Dua Unit', cls.unit_sma, work_contact_id=cls.smp.work_contact_id.id)

    def _wizard(self, pegawai, user, **vals):
        Wizard = self.env['nti_edu.pegawai.akun.wizard'].with_user(user).with_context(
            allowed_company_ids=user.company_ids.ids)
        return Wizard.create(dict(vals, employee_id=pegawai.id))

    def test_buat_akun_dengan_email(self):
        wizard = self._wizard(self.smp, self.tu_dua)
        self.assertEqual(wizard.login, 'budua@contoh.id')
        wizard.action_buat()
        user = self.smp.sudo().user_id
        self.assertTrue(user)
        self.assertFalse(user.share)
        self.assertTrue(user.has_group('nti_edu_base.group_base_pengguna'))
        self.assertFalse(user.has_group('nti_edu_pegawai.group_pegawai_operator'))
        self.assertFalse(user.has_group('nti_edu_pegawai.group_pegawai_hrd'))
        self.assertEqual(user.company_ids, self.unit_smp | self.unit_sma)
        self.assertEqual(user.company_id, self.unit_smp)
        self.assertEqual(user.partner_id, self.smp.work_contact_id)
        self.assertEqual(self.sma.sudo().user_id, user)
        self.assertFalse(wizard.password_awal)
        self.assertEqual(wizard.state, 'selesai')

    def test_tanpa_email_isi_login(self):
        pegawai = self._buat_pegawai('Pak Tanpa Email', self.unit_smp)
        wizard = self._wizard(pegawai, self.tu_smp)
        self.assertFalse(wizard.login)
        with self.assertRaises(UserError):
            wizard.action_buat()
        wizard.login = 'paktanpa'
        wizard.action_buat()
        self.assertTrue(wizard.password_awal)
        self.assertEqual(pegawai.sudo().user_id.login, 'paktanpa')
        wizard.action_tutup()
        self.assertFalse(wizard.password_awal)

    def test_sudah_punya_akun_ditolak(self):
        self._wizard(self.smp, self.tu_dua).action_buat()
        with self.assertRaises(UserError):
            self._wizard(self.smp, self.tu_dua, login='lain').action_buat()

    def test_kontak_sudah_punya_user_ditolak(self):
        pegawai = self._buat_pegawai('Pak Portal', self.unit_smp)
        self.env['res.users'].create({
            'name': 'Pak Portal', 'login': 'pakportal', 'partner_id': pegawai.work_contact_id.id,
            'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        wizard = self._wizard(pegawai, self.tu_smp, login='pakportal2')
        with self.assertRaises(UserError):
            wizard.action_buat()
        self.assertFalse(pegawai.sudo().user_id)

    def test_login_dipakai_ditolak(self):
        pegawai = self._buat_pegawai('Pak Lain', self.unit_smp)
        wizard = self._wizard(pegawai, self.tu_smp, login=self.hrd.login)
        with self.assertRaises(UserError) as ctx:
            wizard.action_buat()
        self.assertNotIn(self.hrd.name, str(ctx.exception))
        self.assertFalse(pegawai.sudo().user_id)

    def test_tu_satu_unit_untuk_pegawai_dua_unit_ditolak(self):
        jumlah = self.env['res.users'].sudo().search_count([])
        wizard = self._wizard(self.smp, self.tu_smp)
        with self.assertRaises(AccessError):
            wizard.action_buat()
        self.assertEqual(self.env['res.users'].sudo().search_count([]), jumlah)
        self.assertFalse(self.smp.sudo().user_id)

    def test_guru_tidak_bisa(self):
        with self.assertRaises(AccessError):
            self._wizard(self.smp, self.guru_smp)

    def test_tombol_membuka_wizard(self):
        aksi = self.smp.with_user(self.tu_dua).action_nti_edu_buat_akun_login()
        self.assertEqual(aksi['res_model'], 'nti_edu.pegawai.akun.wizard')
        self.assertEqual(aksi['context']['default_employee_id'], self.smp.id)
