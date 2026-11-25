# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import NtiPegawaiCommon


@tagged('post_install', '-at_install')
class TestKeluar(NtiPegawaiCommon):
    """Mengarsipkan pegawai mencabut unit itu dari akun; tanpa unit tersisa akun dinonaktifkan."""

    def _akun_dua_unit(self, login='pak_keluar', unit_utama=None):
        """Satu orang, dua penempatan (SMP dan SMA), satu akun yang memegang kedua unit."""
        smp = self._buat_pegawai('Pak Keluar', self.unit_smp, work_email=login + '@contoh.id')
        user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Pak Keluar', 'login': login, 'partner_id': smp.work_contact_id.id,
            'company_id': (unit_utama or self.unit_smp).id,
            'company_ids': [(6, 0, (self.unit_smp | self.unit_sma).ids)],
            'groups_id': [(6, 0, [self.env.ref('nti_edu_base.group_base_pengguna').id])],
        })
        smp.write({'user_id': user.id})
        sma = self._buat_pegawai(
            'Pak Keluar', self.unit_sma, work_contact_id=smp.work_contact_id.id, user_id=user.id)
        return smp, sma, user

    def test_arsip_satu_unit_mencabut_unit_itu(self):
        smp, sma, user = self._akun_dua_unit()
        sma.write({'active': False})
        self.assertEqual(user.company_ids, self.unit_smp)
        self.assertTrue(user.active)
        self.assertEqual(user.company_id, self.unit_smp)

    def test_company_id_pindah_ke_unit_tersisa(self):
        smp, sma, user = self._akun_dua_unit(unit_utama=self.unit_sma)
        self.assertEqual(user.company_id, self.unit_sma)
        sma.write({'active': False})
        self.assertEqual(user.company_ids, self.unit_smp)
        self.assertEqual(user.company_id, self.unit_smp)

    def test_arsip_record_terakhir_menonaktifkan_akun(self):
        smp, sma, user = self._akun_dua_unit()
        sma.write({'active': False})
        smp.write({'active': False})
        self.assertFalse(user.active)

    def test_arsip_dua_record_sekaligus(self):
        smp, sma, user = self._akun_dua_unit()
        (smp | sma).write({'active': False})
        self.assertFalse(user.active)

    def test_arsip_lewat_action_archive_dan_wizard_keberangkatan(self):
        smp, sma, user = self._akun_dua_unit()
        sma.action_archive()
        self.assertEqual(user.company_ids, self.unit_smp)
        wizard = self.env['hr.departure.wizard'].with_context(
            active_id=smp.id, toggle_active=True).create({
                'employee_id': smp.id,
                'departure_reason_id': self.env['hr.departure.reason'].search([], limit=1).id,
            })
        wizard.action_register_departure()
        self.assertFalse(smp.active)
        self.assertFalse(user.active)

    def test_tu_unit_mengarsipkan_pegawai_unitnya(self):
        smp, sma, user = self._akun_dua_unit()
        sma.with_user(self.tu_sma).with_context(
            allowed_company_ids=self.tu_sma.company_ids.ids).write({'active': False})
        self.assertEqual(user.company_ids, self.unit_smp)

    def test_aktifkan_lagi_tidak_mengaktifkan_akun(self):
        smp, sma, user = self._akun_dua_unit()
        (smp | sma).write({'active': False})
        self.assertFalse(user.active)
        smp.write({'active': True})
        self.assertFalse(user.active)

    def test_pegawai_tanpa_akun_diarsipkan(self):
        pegawai = self._buat_pegawai('Tanpa Akun', self.unit_smp)
        pegawai.write({'active': False})
        self.assertFalse(pegawai.active)

    def test_admin_sistem_tidak_dicabut(self):
        admin = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Admin Tes', 'login': 'admin_keluar', 'company_id': self.unit_smp.id,
            'company_ids': [(6, 0, (self.unit_smp | self.unit_sma).ids)],
            'groups_id': [(6, 0, [self.env.ref('base.group_system').id])],
        })
        pegawai = self._buat_pegawai(
            'Admin Pegawai', self.unit_sma, work_contact_id=admin.partner_id.id, user_id=admin.id)
        pegawai.write({'active': False})
        self.assertEqual(admin.company_ids, self.unit_smp | self.unit_sma)
        self.assertTrue(admin.active)

    def test_yayasan_tidak_dicabut(self):
        smp, sma, user = self._akun_dua_unit()
        user.write({'company_ids': [(4, self.yayasan.id)]})
        sma.write({'active': False})
        self.assertEqual(user.company_ids, self.unit_smp | self.yayasan)

    def _unit_smk(self):
        return self.env['res.company'].create({
            'name': 'SMK Pegawai Tes', 'parent_id': self.yayasan.id, 'nti_edu_jenis': 'unit',
            'nti_edu_jenjang_id': self.env.ref('nti_edu_base.jenjang_sma').id, 'nti_edu_kode': 'pgsmk',
        })

    def _arsip_oleh(self, pegawai, user):
        pegawai.with_user(user).with_context(allowed_company_ids=user.company_ids.ids).write({'active': False})

    def test_hanya_unit_yang_diarsip_dicabut(self):
        smk = self._unit_smk()
        smp, sma, user = self._akun_dua_unit()
        user.write({'company_ids': [(4, smk.id)]})
        sma.write({'active': False})
        self.assertEqual(user.company_ids, self.unit_smp | smk)
        self.assertTrue(user.active)

    def test_tu_tak_menonaktifkan_akun_dengan_unit_lain(self):
        pegawai = self._buat_pegawai('Pak Satu', self.unit_smp, work_email='satu@contoh.id')
        user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Pak Satu', 'login': 'pak_satu', 'partner_id': pegawai.work_contact_id.id,
            'company_id': self.unit_smp.id,
            'company_ids': [(6, 0, (self.unit_smp | self.unit_sma).ids)],
            'groups_id': [(6, 0, [self.env.ref('nti_edu_base.group_base_pengguna').id])],
        })
        pegawai.write({'user_id': user.id})
        self._arsip_oleh(pegawai, self.tu_smp)
        self.assertEqual(user.company_ids, self.unit_sma)
        self.assertEqual(user.company_id, self.unit_sma)
        self.assertTrue(user.active)

    def test_tu_menonaktifkan_akun_bila_semua_unit_miliknya(self):
        pegawai = self._buat_pegawai('Pak Satu', self.unit_smp, work_email='satu@contoh.id')
        user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Pak Satu', 'login': 'pak_satu', 'partner_id': pegawai.work_contact_id.id,
            'company_id': self.unit_smp.id, 'company_ids': [(6, 0, self.unit_smp.ids)],
            'groups_id': [(6, 0, [self.env.ref('nti_edu_base.group_base_pengguna').id])],
        })
        pegawai.write({'user_id': user.id})
        self._arsip_oleh(pegawai, self.tu_smp)
        self.assertFalse(user.active)

    def test_akun_admin_dasar_tidak_disentuh(self):
        admin = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Admin Dasar', 'login': 'admin_dasar', 'company_id': self.unit_smp.id,
            'company_ids': [(6, 0, (self.unit_smp | self.unit_sma).ids)],
            'groups_id': [(6, 0, [self.env.ref('nti_edu_base.group_base_admin').id])],
        })
        pegawai = self._buat_pegawai(
            'Admin Dasar', self.unit_sma, work_contact_id=admin.partner_id.id, user_id=admin.id)
        pegawai.write({'active': False})
        self.assertEqual(admin.company_ids, self.unit_smp | self.unit_sma)
        self.assertTrue(admin.active)

    def test_akun_hrd_hanya_dinonaktifkan_oleh_hrd(self):
        pegawai = self._buat_pegawai(
            'Bu HRD', self.unit_smp, work_contact_id=self.hrd.partner_id.id, user_id=self.hrd.id)
        self.hrd.write({'company_ids': [(3, self.unit_sma.id)], 'company_id': self.unit_smp.id})
        self._arsip_oleh(pegawai, self.tu_smp)
        self.assertTrue(self.hrd.active)

    def test_arsip_diri_sendiri_ditolak(self):
        pegawai = self._buat_pegawai(
            'Bu HRD', self.unit_smp, work_contact_id=self.hrd.partner_id.id, user_id=self.hrd.id)
        self.hrd.write({'company_ids': [(3, self.unit_sma.id)], 'company_id': self.unit_smp.id})
        with self.assertRaises(UserError):
            self._arsip_oleh(pegawai, self.hrd)
