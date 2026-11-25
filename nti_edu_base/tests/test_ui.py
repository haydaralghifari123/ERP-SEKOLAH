# -*- coding: utf-8 -*-
from datetime import date

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestUiDataSekolah(HttpCase):
    """Uji asap di browser: setiap layar Data Sekolah harus terbuka tanpa galat klien."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        env['nti_edu.tahun.ajaran'].search([('is_aktif', '=', True)]).write({'is_aktif': False})
        yayasan = env['res.company'].create({'name': 'Yayasan Uji UI', 'nti_edu_jenis': 'yayasan'})
        cls.unit = env['res.company'].create({
            'name': 'SMP Uji UI', 'parent_id': yayasan.id, 'nti_edu_jenis': 'unit',
            'nti_edu_jenjang_id': env.ref('nti_edu_base.jenjang_smp').id, 'nti_edu_kode': 'smpui',
        })
        tahun = env['nti_edu.tahun.ajaran'].create({
            'name': '2026/2027', 'tanggal_mulai': date(2026, 7, 13), 'tanggal_selesai': date(2027, 6, 30),
            'is_aktif': True})
        env['nti_edu.rombel'].create({
            'name': 'VII UI', 'tahun_ajaran_id': tahun.id, 'company_id': cls.unit.id,
            'tingkat_id': env.ref('nti_edu_base.tingkat_smp_7').id})
        siswa = env['res.partner'].create({
            'name': 'Siswa Uji UI', 'nti_edu_is_siswa': True, 'company_id': cls.unit.id, 'nti_edu_nis': 'UI001'})
        wali = env['res.partner'].create({'name': 'Wali Uji UI', 'email': 'wali.ui@example.com'})
        env['nti_edu.siswa.wali'].create({'siswa_id': siswa.id, 'partner_id': wali.id, 'hubungan': 'ayah'})
        env['nti_edu.hari.libur'].create({
            'name': 'Libur Uji UI', 'tanggal_mulai': date(2026, 8, 17), 'company_id': cls.unit.id})
        cls._buat_user('ui_admin', 'nti_edu_base.group_base_admin')
        cls._buat_user('ui_operator', 'nti_edu_base.group_base_operator')

    @classmethod
    def _buat_user(cls, login, grup):
        # Kata sandi = login: dibutuhkan untuk authenticate pada HttpCase.
        return cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': login, 'login': login, 'password': login,
            'company_id': cls.unit.id, 'company_ids': [(6, 0, cls.unit.ids)],
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id, cls.env.ref(grup).id])],
        })

    def test_admin(self):
        self.start_tour('/odoo', 'nti_edu_base_asap', login='ui_admin', timeout=120)

    def test_operator(self):
        self.start_tour('/odoo', 'nti_edu_base_asap_operator', login='ui_operator', timeout=120)
