# -*- coding: utf-8 -*-
from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests import Form, new_test_user, tagged
from odoo.tools.safe_eval import safe_eval

from .common import NtiEduCommon

ACTIONS = [
    'action_siswa', 'action_rombel', 'action_wali', 'action_tahun_ajaran', 'action_hari_libur',
    'action_unit', 'action_jenjang', 'action_jurusan', 'action_mapel', 'action_ruang',
]

ACTIONS_ADMIN = ['action_unit', 'action_jenjang', 'action_jurusan', 'action_mapel', 'action_ruang']


@tagged('post_install', '-at_install')
class TestTampilan(NtiEduCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_admin = new_test_user(
            cls.env, login='tes_admin_data', groups='nti_edu_base.group_base_admin',
            company_id=cls.unit_smp.id,
            company_ids=[(6, 0, (cls.yayasan | cls.unit_smp | cls.unit_sma).ids)])

    def _leluhur(self, menu):
        hasil = self.env['ir.ui.menu']
        while menu.parent_id:
            menu = menu.parent_id
            hasil |= menu
        return hasil

    def _action_terlihat(self, user):
        """Action dari menu yang terlihat oleh user (dengan akar menu data sekolah)."""
        ids = self.env['ir.ui.menu'].with_user(user)._visible_menu_ids()
        menus = self.env['ir.ui.menu'].browse(ids).filtered(
            lambda m: all(p.id in ids for p in self._leluhur(m)) and m.action and m.action._name == 'ir.actions.act_window'
            and m.action.get_external_id().get(m.action.id, '').startswith('nti_edu_base.action_'))
        return menus.mapped('action')

    def _view_untuk_mode(self, action, mode):
        view = action.view_ids.filtered(lambda v: v.view_mode == mode).view_id
        if not view and action.view_id and action.view_id.type == mode:
            view = action.view_id
        return view

    def test_semua_action_terbuka(self):
        diharapkan = {
            self.user_operator_smp: set(ACTIONS) - set(ACTIONS_ADMIN),
            self.user_guru_smp: set(ACTIONS) - set(ACTIONS_ADMIN) - {'action_wali'},
            self.user_admin: set(ACTIONS),
        }
        for user, nama in diharapkan.items():
            ditemukan = self._action_terlihat(user)
            xmlids = {a.get_external_id()[a.id].split('.', 1)[1] for a in ditemukan}
            self.assertEqual(xmlids & set(ACTIONS), nama, user.login)
            for action in ditemukan:
                xmlid = action.get_external_id()[action.id]
                model = self.env[action.res_model].with_user(user)
                with self.subTest(user=user.login, action=xmlid):
                    self.assertTrue(model.has_access('read'))
                    domain = safe_eval(action.domain or '[]', {'uid': user.id, 'allowed_company_ids': user.company_ids.ids})
                    konteks = safe_eval(action.context or '{}', {'uid': user.id, 'active_id': False})
                    self.assertIsInstance(konteks, dict)
                    model.search_read(domain, ['id'], limit=1)
                    for mode in action.view_mode.split(','):
                        view = self._view_untuk_mode(action, mode)
                        hasil = model.get_views([(view.id or False, mode)])
                        self.assertIn(mode, hasil['views'])

    def test_tombol_ada_di_view(self):
        aksi = self.env.ref('nti_edu_base.action_kenaikan_kelas_wizard')
        arch = self.env['nti_edu.rombel'].with_user(self.user_operator_smp).get_views(
            [(self.env.ref('nti_edu_base.view_rombel_form').id, 'form')])['views']['form']['arch']
        form = etree.fromstring(arch)
        tombol = form.xpath('//button[@name=$n and @type="action"]', n=str(aksi.id))
        self.assertEqual(len(tombol), 1)
        arch = self.env['res.partner'].with_user(self.user_operator_smp).get_views(
            [(self.env.ref('nti_edu_base.view_siswa_form').id, 'form')])['views']['form']['arch']
        form = etree.fromstring(arch)
        tombol = form.xpath(
            '//field[@name="nti_edu_wali_ids"]//list/button[@name="action_buat_akun_portal" and @type="object"]')
        self.assertEqual(len(tombol), 1)

    def test_kanban_tanpa_helper_lama(self):
        """Kanban Odoo 18 bergaya `card` tidak punya `kanban_image`/`user_context` (hanya ada di arsitektur lama);
        memakainya membuat web client galat saat merender kartu."""
        views = self.env['ir.ui.view'].search([('type', '=', 'kanban')]).filtered(
            lambda v: v.get_external_id().get(v.id, '').startswith('nti_edu_base.'))
        self.assertTrue(views, 'Modul seharusnya punya minimal satu view kanban.')
        for view in views:
            with self.subTest(view=view.get_external_id()[view.id]):
                arch = self.env[view.model].get_views([(view.id, 'kanban')])['views']['kanban']['arch']
                kanban = etree.fromstring(arch)
                if kanban.xpath('//t[@t-name="card"]'):
                    for atribut in kanban.xpath('//@*'):
                        self.assertNotRegex(atribut, r'\b(kanban_image|user_context)\b')
        kanban = etree.fromstring(self.env['res.partner'].get_views(
            [(self.env.ref('nti_edu_base.view_siswa_kanban').id, 'kanban')])['views']['kanban']['arch'])
        self.assertEqual(len(kanban.xpath('//field[@name="avatar_128" and @widget="image"]')), 1)

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
        with self.assertRaisesRegex(AccessError, 'Operator Data Sekolah'):
            wali.with_user(self.user_guru_smp).action_nti_edu_buat_akun_portal()
        # Lapisan yang menolak guru: cek operator di partner (partner_id sudah ada di cache, jadi ACL
        # nti_edu.siswa.wali tidak sempat dipicu pada pembacaan field).
        with self.assertRaisesRegex(AccessError, 'Operator Data Sekolah'):
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

    def test_menu_wali_khusus_operator_dan_per_unit(self):
        Menu = self.env['ir.ui.menu']
        menu = self.env.ref('nti_edu_base.menu_wali')
        self.assertNotIn(menu.id, Menu.with_user(self.user_guru_smp)._visible_menu_ids())
        self.assertIn(menu.id, Menu.with_user(self.user_operator_smp)._visible_menu_ids())
        siswa_smp = self._buat_siswa('Anak SMP', self.unit_smp, 'W001')
        siswa_sma = self._buat_siswa('Anak SMA', self.unit_sma, 'W002')
        Wali = self.env['nti_edu.siswa.wali']
        wali_smp = self.env['res.partner'].create({'name': 'Wali SMP'})
        wali_sma = self.env['res.partner'].create({'name': 'Wali SMA'})
        Wali.create({'siswa_id': siswa_smp.id, 'partner_id': wali_smp.id})
        Wali.create({'siswa_id': siswa_sma.id, 'partner_id': wali_sma.id})
        aksi = self.env.ref('nti_edu_base.action_wali')
        user = self.user_operator_smp
        domain = safe_eval(aksi.domain, {'uid': user.id, 'allowed_company_ids': user.company_ids.ids})
        hasil = self.env['res.partner'].with_user(user).search(domain)
        self.assertIn(wali_smp, hasil)
        self.assertNotIn(wali_sma, hasil)
