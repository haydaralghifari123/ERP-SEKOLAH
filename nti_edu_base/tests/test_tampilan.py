# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError
from odoo.tests import Form, new_test_user, tagged
from odoo.tools.safe_eval import safe_eval

from .common import NtiEduCommon

ACTIONS = [
    'action_siswa', 'action_rombel', 'action_wali', 'action_tahun_ajaran', 'action_hari_libur',
    'action_unit', 'action_jenjang', 'action_jurusan', 'action_mapel', 'action_ruang',
]


@tagged('post_install', '-at_install')
class TestTampilan(NtiEduCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_admin = new_test_user(
            cls.env, login='tes_admin_data', groups='nti_edu_base.group_base_admin',
            company_id=cls.unit_smp.id,
            company_ids=[(6, 0, (cls.yayasan | cls.unit_smp | cls.unit_sma).ids)])

    def test_semua_action_terbuka(self):
        for user in (self.user_operator_smp, self.user_guru_smp, self.user_admin):
            for xmlid in ACTIONS:
                action = self.env.ref('nti_edu_base.' + xmlid)
                model = self.env[action.res_model].with_user(user)
                if not model.has_access('read'):
                    continue
                domain = safe_eval(action.domain or '[]', {'uid': user.id})
                safe_eval(action.context or '{}', {'uid': user.id, 'active_id': False})
                with self.subTest(user=user.login, action=xmlid):
                    model.search_read(domain, ['id'], limit=1)
                    for mode in action.view_mode.split(','):
                        view = action.view_ids.filtered(lambda v: v.view_mode == mode).view_id
                        hasil = model.get_views([(view.id or False, mode)])
                        self.assertIn(mode, hasil['views'])

    def test_admin_data_sekolah_ubah_unit(self):
        unit = self.unit_smp.with_user(self.user_admin)
        unit.write({'nti_edu_kode': 'smpx', 'nti_edu_hari_sekolah': '6'})
        self.assertEqual(self.unit_smp.nti_edu_kode, 'smpx')
        with self.assertRaises(AccessError):
            self.unit_smp.with_user(self.user_guru_smp).write({'nti_edu_kode': 'zzz'})
        with self.assertRaises(AccessError):
            self.env['res.company'].with_user(self.user_admin).create({'name': 'Baru'})

    def test_tombol_akun_portal_wali(self):
        siswa = self._buat_siswa('Siswa Wali', self.unit_smp, '010')
        wali = self.env['res.partner'].create({'name': 'Wali Tes', 'email': 'wali.tes@example.com'})
        wali2 = self.env['res.partner'].create({'name': 'Wali Dua', 'email': 'wali.dua@example.com'})
        Wali = self.env['nti_edu.siswa.wali']
        baris = Wali.create({'siswa_id': siswa.id, 'partner_id': wali.id})
        baris2 = Wali.create({'siswa_id': siswa.id, 'partner_id': wali2.id})
        aksi = baris.with_user(self.user_operator_smp).action_buat_akun_portal()
        self.assertEqual(aksi['res_model'], 'nti_edu.akun.portal.wizard')
        self.assertEqual(aksi['context']['default_partner_id'], wali.id)
        with self.assertRaises(AccessError):
            baris.with_user(self.user_guru_smp).action_buat_akun_portal()
        with self.assertRaises(ValueError):
            (baris | baris2).action_buat_akun_portal()

    def test_form_rombel_dan_kenaikan(self):
        tahun = self.env['nti_edu.tahun.ajaran'].create({
            'name': '2026/2027', 'tanggal_mulai': '2026-07-01', 'tanggal_selesai': '2027-06-30'})
        tingkat = self.env['nti_edu.tingkat'].create({
            'name': 'VII', 'jenjang_id': self.env.ref('nti_edu_base.jenjang_smp').id})
        rombel = self.env['nti_edu.rombel'].create({
            'name': '7A', 'tahun_ajaran_id': tahun.id, 'tingkat_id': tingkat.id,
            'company_id': self.unit_smp.id})
        form = Form(rombel.with_user(self.user_operator_smp), view='nti_edu_base.view_rombel_form')
        self.assertEqual(form.name, '7A')
        aksi = self.env.ref('nti_edu_base.action_kenaikan_kelas_wizard')
        konteks = safe_eval(aksi.context, {'active_id': rombel.id})
        self.assertEqual(konteks['default_rombel_asal_id'], rombel.id)
        wizard = self.env['nti_edu.kenaikan.kelas.wizard'].with_user(self.user_operator_smp).with_context(
            **konteks).create({})
        self.assertEqual(wizard.rombel_asal_id, rombel)

    def test_menu_konfigurasi_khusus_admin(self):
        menu = self.env.ref('nti_edu_base.menu_konfigurasi')
        admin = self._buat_user('tes_admin_smp', 'nti_edu_base.group_base_admin', self.unit_smp)
        Menu = self.env['ir.ui.menu']
        self.assertNotIn(menu.id, Menu.with_user(self.user_operator_smp)._visible_menu_ids())
        self.assertIn(menu.id, Menu.with_user(admin)._visible_menu_ids())
        root = self.env.ref('nti_edu_base.menu_data_sekolah')
        self.assertIn(root.id, Menu.with_user(self.user_guru_smp)._visible_menu_ids())

    def test_form_siswa_guru(self):
        siswa = self._buat_siswa('Siswa Tampil', self.unit_smp, '001')
        form = Form(siswa.with_user(self.user_guru_smp), view='nti_edu_base.view_siswa_form')
        self.assertEqual(form.name, 'Siswa Tampil')

    def test_form_siswa_operator(self):
        siswa = self._buat_siswa('Siswa Tampil 2', self.unit_smp, '002')
        form = Form(siswa.with_user(self.user_operator_smp), view='nti_edu_base.view_siswa_form')
        self.assertEqual(form.nti_edu_nis, '002')
