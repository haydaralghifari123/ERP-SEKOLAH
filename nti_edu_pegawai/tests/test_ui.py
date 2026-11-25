# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestUiPegawai(HttpCase):
    """Uji asap di browser: layar Pegawai harus terbuka tanpa galat klien, sertifikasi tersimpan,
    dan kedua wizard (Buat Akun Login, Tempatkan di Unit Lain) bisa dibuka lalu dibatalkan."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        yayasan = env['res.company'].create({'name': 'Yayasan Uji UI Pegawai', 'nti_edu_jenis': 'yayasan'})
        Company = env['res.company']
        cls.unit_a = Company.create({
            'name': 'SMP Uji UI Pegawai', 'parent_id': yayasan.id, 'nti_edu_jenis': 'unit',
            'nti_edu_jenjang_id': env.ref('nti_edu_base.jenjang_smp').id, 'nti_edu_kode': 'uipga'})
        cls.unit_b = Company.create({
            'name': 'SMA Uji UI Pegawai', 'parent_id': yayasan.id, 'nti_edu_jenis': 'unit',
            'nti_edu_jenjang_id': env.ref('nti_edu_base.jenjang_sma').id, 'nti_edu_kode': 'uipgb'})
        Employee = env['hr.employee'].with_context(tracking_disable=True)
        # Orang dengan email, bekerja di kedua unit, tanpa akun: tombol Buat Akun Login tampil.
        kontak = env['res.partner'].create({'name': 'Pegawai Dua Unit UI', 'email': 'dua.unit.ui@example.com'})
        cls.pegawai_dua = Employee.create([
            {'name': 'Pegawai Dua Unit UI', 'company_id': cls.unit_a.id, 'work_contact_id': kontak.id,
             'nti_edu_jenis_ptk': 'guru_mapel'},
            {'name': 'Pegawai Dua Unit UI', 'company_id': cls.unit_b.id, 'work_contact_id': kontak.id,
             'nti_edu_jenis_ptk': 'guru_mapel'},
        ])
        cls.kontak = kontak
        # Orang hanya di satu unit: target untuk Tempatkan di Unit Lain.
        Employee.create({'name': 'Pegawai Satu Unit UI', 'company_id': cls.unit_a.id, 'nti_edu_jenis_ptk': 'guru_kelas'})
        # Kata sandi = login: dibutuhkan untuk authenticate pada HttpCase.
        env['res.users'].with_context(no_reset_password=True).create({
            'name': 'ui_tu_dua', 'login': 'ui_tu_dua', 'password': 'ui_tu_dua',
            'company_id': cls.unit_a.id, 'company_ids': [(6, 0, (cls.unit_a | cls.unit_b).ids)],
            'groups_id': [(6, 0, [
                env.ref('base.group_user').id, env.ref('nti_edu_pegawai.group_pegawai_operator').id])],
        })

    def test_tu_dua_unit(self):
        self.start_tour('/odoo', 'nti_edu_pegawai_asap', login='ui_tu_dua', timeout=120)
        sertifikasi = self.env['nti_edu.pegawai.sertifikasi'].search([('nomor', '=', 'SERT-TOUR-1')])
        self.assertEqual(sertifikasi.partner_id, self.kontak)
        # Wizard hanya dibuka lalu dibatalkan: tidak ada akun dan tidak ada penempatan baru.
        self.assertFalse(self.env['res.users'].with_context(active_test=False).search([('login', '=', 'dua.unit.ui@example.com')]))
        self.assertEqual(self.env['hr.employee'].search_count([('name', '=', 'Pegawai Satu Unit UI')]), 1)
