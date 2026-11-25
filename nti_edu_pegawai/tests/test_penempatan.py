# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import NtiPegawaiCommon


@tagged('post_install', '-at_install')
class TestPenempatan(NtiPegawaiCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pegawai = cls._buat_pegawai('Pak Pindah', cls.unit_smp, work_email='pindah@contoh.id')
        cls.pegawai.work_contact_id.sudo().write({'nti_edu_nuptk': '9988776655443322'})

    def _wizard(self, pegawai, user, unit, **vals):
        Wizard = self.env['nti_edu.pegawai.penempatan.wizard'].with_user(user).with_context(
            allowed_company_ids=user.company_ids.ids)
        return Wizard.create(dict(vals, employee_id=pegawai.id, company_id=unit.id))

    def _buat_user_untuk(self, pegawai):
        user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Pak Pindah', 'login': 'pak_pindah', 'partner_id': pegawai.work_contact_id.id,
            'company_id': self.unit_smp.id, 'company_ids': [(6, 0, self.unit_smp.ids)],
            'groups_id': [(6, 0, [self.env.ref('nti_edu_base.group_base_pengguna').id])],
        })
        pegawai.write({'user_id': user.id})
        return user

    def _di_unit(self, unit):
        return self.env['hr.employee'].sudo().with_context(active_test=False).search([
            ('work_contact_id', '=', self.pegawai.work_contact_id.id), ('company_id', '=', unit.id)])

    def test_tempatkan_dengan_akun(self):
        user = self._buat_user_untuk(self.pegawai)
        wizard = self._wizard(self.pegawai, self.tu_dua, self.unit_sma, nti_edu_jenis_ptk='guru_mapel')
        aksi = wizard.action_tempatkan()
        baru = self._di_unit(self.unit_sma)
        self.assertEqual(len(baru), 1)
        self.assertEqual(baru.user_id, user)
        self.assertEqual(baru.nti_edu_jenis_ptk, 'guru_mapel')
        self.assertIn(self.unit_sma, user.company_ids)
        self.assertIn(self.unit_smp, user.company_ids)
        self.assertFalse(self.pegawai.work_contact_id.sudo().company_id)
        self.assertEqual(aksi['res_id'], baru.id)
        self.assertEqual(aksi['res_model'], 'hr.employee')
        rec = baru.with_user(self.tu_sma).with_context(allowed_company_ids=self.tu_sma.company_ids.ids)
        self.assertEqual(rec.nti_edu_nuptk, '9988776655443322')

    def test_tempatkan_tanpa_akun(self):
        self._wizard(self.pegawai, self.tu_dua, self.unit_sma).action_tempatkan()
        baru = self._di_unit(self.unit_sma)
        self.assertEqual(len(baru), 1)
        self.assertFalse(baru.user_id)

    def test_tu_tanpa_unit_tujuan_ditolak(self):
        with self.assertRaises(AccessError):
            self._wizard(self.pegawai, self.tu_smp, self.unit_sma).action_tempatkan()
        self.assertFalse(self._di_unit(self.unit_sma))

    def test_hrd_boleh_menempatkan(self):
        self._wizard(self.pegawai, self.hrd, self.unit_sma).action_tempatkan()
        self.assertTrue(self._di_unit(self.unit_sma))

    def test_tujuan_bukan_unit_ditolak(self):
        with self.assertRaises(UserError):
            self._wizard(self.pegawai, self.hrd, self.yayasan).action_tempatkan()

    def test_sudah_di_unit_itu_ditolak(self):
        with self.assertRaises(UserError):
            self._wizard(self.pegawai, self.tu_dua, self.unit_smp).action_tempatkan()

    def test_tempatkan_kembali_ke_unit_lama_mengaktifkan_arsip(self):
        user = self._buat_user_untuk(self.pegawai)
        self._wizard(self.pegawai, self.tu_dua, self.unit_sma).action_tempatkan()
        lama = self._di_unit(self.unit_sma)
        lama.write({'active': False})
        aksi = self._wizard(
            self.pegawai, self.tu_dua, self.unit_sma, nti_edu_jenis_ptk='laboran').action_tempatkan()
        lama.invalidate_recordset()
        self.assertTrue(lama.active)
        self.assertEqual(lama.nti_edu_jenis_ptk, 'laboran')
        self.assertEqual(lama.user_id, user)
        self.assertEqual(aksi['res_id'], lama.id)
        self.assertEqual(len(self._di_unit(self.unit_sma)), 1)
