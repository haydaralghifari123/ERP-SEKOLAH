# -*- coding: utf-8 -*-
from datetime import date
from unittest.mock import patch

import psycopg2

from odoo.exceptions import AccessError
from odoo.tests import freeze_time, tagged
from odoo.tests.common import new_test_user

from .common import NtiTagihanCommon


@tagged('post_install', '-at_install')
class TestLaporan(NtiTagihanCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ref = cls.env.ref
        cls.Move = cls.env['account.move']
        cls.Mesin = cls.env['nti_edu.tagihan.mesin']
        cls.Mail = cls.env['mail.mail']
        cls.juni = ref('nti_edu_tagihan.bulan_06')
        cls.periode_bulanan = cls.env['nti_edu.tagihan.periode.jenis'].create({
            'name': 'Bulanan Laporan', 'dasar': 'bulan', 'jumlah_bulan': 1, 'hari_terbit': 1,
            'hari_jatuh_tempo': 10, 'bulan_libur_ids': [(6, 0, cls.juni.ids)]})
        cls.spp = cls._buat_komponen('SPP Laporan', None, periode_jenis_id=cls.periode_bulanan.id)
        cls.aturan_cicil = cls.env['nti_edu.tagihan.aturan.cicilan'].create({
            'name': 'Cicil 2x Laporan', 'maks_kali': 2, 'jarak': 1, 'jarak_satuan': 'bulan'})
        cls.pangkal = cls._buat_komponen(
            'Pangkal Laporan', 'periode_sekali', aturan_cicilan_id=cls.aturan_cicil.id)
        cls.komponen_denda = cls._buat_komponen('Denda Laporan', None, jenis='denda')
        cls.beasiswa = cls.env['nti_edu.tagihan.potongan.jenis'].create({
            'name': 'Beasiswa Laporan', 'tipe': 'nominal', 'nilai_bawaan': 25000,
            'komponen_ids': [(6, 0, cls.spp.ids)]})
        cls.rekening_smp = cls._buat_rekening(cls.unit_smp)

    # --- bantuan ---------------------------------------------------------------------------

    def _spp(self, bulan, siswa=None, nominal=150000, potongan=(), tahun=2026):
        periode = date(tahun, bulan, 1)
        return self.Move._nti_edu_terbitkan(
            siswa or self.siswa_a, self.spp, nominal, periode, periode.replace(day=10), potongan=potongan,
            periode=periode, tahun_ajaran_id=self.ta)

    def _email(self, partner, subjek):
        return self.Mail.search([
            ('model', '=', 'res.partner'), ('res_id', '=', partner.id), ('recipient_ids', 'in', partner.ids),
            ('subject', 'ilike', subjek)])

    def _catatan(self, tagihan, teks):
        return tagihan.message_ids.filtered(lambda m: teks in (m.body or ''))

    # --- kartu SPP ---------------------------------------------------------------------------

    def test_data_kartu(self):
        juli = self._spp(7, potongan=[(self.beasiswa, 25000)])
        agustus = self._spp(8)
        september = self._spp(9)
        self.Mesin._bayar(juli, 125000, self.rekening_smp, date(2026, 7, 8), 'SPP Juli')
        self.Mesin._bayar(agustus, 50000, self.rekening_smp, date(2026, 8, 5), 'SPP Agustus')
        pangkal = self.Move._nti_edu_terbitkan(
            self.siswa_a, self.pangkal, 1000000, date(2026, 7, 1), date(2026, 7, 10), tahun_ajaran_id=self.ta)
        pangkal._nti_edu_atur_cicilan(2)
        self.Mesin._bayar(pangkal, 500000, self.rekening_smp, date(2026, 7, 9), 'Cicilan 1')
        denda = self.Move._nti_edu_terbitkan(
            self.siswa_a, self.komponen_denda, 10000, date(2026, 8, 18), date(2026, 8, 18),
            tagihan_asal_id=agustus, denda_jatuh_tempo=date(2026, 8, 10), denda_bulan_ke=1)
        self.Mesin._bayar_sebagai_kredit(
            self.siswa_a, self.unit_smp, 50000, self.rekening_smp, date(2026, 8, 20), 'Titipan')
        # Tagihan siswa lain dan tagihan batal tidak ikut.
        self._spp(7, siswa=self.siswa_b)
        batal = self._spp(10)
        batal._nti_edu_batalkan('Salah terbit')

        data = self.siswa_a._nti_edu_data_kartu_spp(self.ta)
        self.assertEqual(data['bulan'][0], date(2026, 7, 1))
        self.assertEqual(data['bulan'][-1], date(2027, 6, 1))
        self.assertEqual(len(data['bulan']), 12)
        self.assertEqual(len(data['bulanan']), 1)
        baris = data['bulanan'][0]
        self.assertEqual(baris['komponen'], self.spp)
        sel = baris['sel']
        self.assertEqual(len(sel), 12)
        self.assertEqual(
            [s['status'] for s in sel],
            ['lunas', 'sebagian', 'belum'] + ['belum_terbit'] * 8 + ['libur'])
        self.assertEqual(sel[0]['tagihan'], juli)
        self.assertEqual(sel[0]['nominal'], 150000)
        self.assertEqual(sel[0]['potongan'], 25000)
        self.assertEqual(sel[0]['sisa'], 0)
        self.assertEqual(sel[0]['tanggal_lunas'], date(2026, 7, 8))
        self.assertEqual((sel[1]['nominal'], sel[1]['potongan'], sel[1]['sisa']), (150000, 0, 100000))
        self.assertFalse(sel[1]['tanggal_lunas'])
        self.assertEqual(sel[2]['sisa'], 150000)
        self.assertFalse(sel[3]['tagihan'])

        lainnya = {item['tagihan']: item for item in data['lainnya']}
        self.assertEqual(set(lainnya), {pangkal, denda})
        self.assertEqual(lainnya[pangkal]['status'], 'sebagian')
        self.assertEqual(lainnya[pangkal]['sisa'], 500000)
        self.assertEqual(
            [(c['jatuh_tempo'], c['nominal'], c['sisa']) for c in lainnya[pangkal]['cicilan']],
            [(date(2026, 7, 10), 500000, 0), (date(2026, 8, 10), 500000, 500000)])
        self.assertEqual((lainnya[denda]['status'], lainnya[denda]['sisa']), ('belum', 10000))

        self.assertEqual(data['total_tagihan'], 125000 + 150000 + 150000 + 1000000 + 10000)
        self.assertEqual(data['total_bayar'], 125000 + 50000 + 500000)
        self.assertEqual(data['sisa'], 100000 + 150000 + 500000 + 10000)
        self.assertEqual(data['saldo_kredit'], 50000)

        html, _format = self.env['ir.actions.report']._render_qweb_pdf(
            'nti_edu_tagihan.action_report_kartu_spp', self.siswa_a.ids)
        self.assertIn(b'SPP Laporan', html)
        self.assertIn(b'Pangkal Laporan', html)
        # Pemantau unit siswa boleh mencetak; guru tanpa grup tagihan tidak.
        self.env['ir.actions.report'].with_user(self.pemantau_smp)._render_qweb_pdf(
            'nti_edu_tagihan.action_report_kartu_spp', self.siswa_a.ids)
        with self.assertRaises(AccessError):
            self.env['ir.actions.report'].with_user(self.user_guru_smp)._render_qweb_pdf(
                'nti_edu_tagihan.action_report_kartu_spp', self.siswa_a.ids)

    def test_tab_keuangan_hak(self):
        spp = self._spp(7)
        potongan = self.env['nti_edu.tagihan.potongan'].create({
            'siswa_id': self.siswa_a.id, 'jenis_id': self.beasiswa.id, 'nilai': 25000,
            'tanggal_mulai': date(2026, 7, 1)})
        potongan.action_ajukan()
        self.assertEqual(potongan.state, 'aktif')
        with self.assertRaises(AccessError):
            self.siswa_a.with_user(self.user_guru_smp).read(['nti_edu_sisa_tagihan'])
        with freeze_time('2026-08-01'):
            siswa = self.siswa_a.with_user(self.pemantau_smp)
            nilai = siswa.read(['nti_edu_sisa_tagihan', 'nti_edu_tunggakan', 'nti_edu_saldo_kredit'])[0]
            self.assertEqual(nilai['nti_edu_sisa_tagihan'], 150000)
            self.assertEqual(nilai['nti_edu_tunggakan'], 150000)
            self.assertEqual(siswa.nti_edu_tagihan_ids, spp)
            self.assertEqual(siswa.nti_edu_potongan_ids, potongan)
        with freeze_time('2026-07-05'):
            self.siswa_a.invalidate_recordset()
            self.assertEqual(self.siswa_a.nti_edu_tunggakan, 0)
            self.assertEqual(self.siswa_a.nti_edu_sisa_tagihan, 150000)
        # Tab Keuangan di form siswa hanya untuk grup tagihan.
        arsitektur = self.env['res.partner'].with_user(self.pemantau_smp).get_views(
            [(self.env.ref('nti_edu_base.view_siswa_form').id, 'form')])['views']['form']['arch']
        self.assertIn('nti_edu_sisa_tagihan', arsitektur)
        arsitektur = self.env['res.partner'].with_user(self.user_guru_smp).get_views(
            [(self.env.ref('nti_edu_base.view_siswa_form').id, 'form')])['views']['form']['arch']
        self.assertNotIn('nti_edu_sisa_tagihan', arsitektur)

    # --- tunggakan ---------------------------------------------------------------------------

    def test_umur(self):
        Move = self.Move
        with freeze_time('2026-09-24'):
            # Jatuh tempo 10 Agustus = 45 hari lalu.
            spp = self._spp(8)
            self.assertEqual(spp.nti_edu_jatuh_tempo_terbuka, date(2026, 8, 10))
            self.assertEqual(spp.nti_edu_umur_tunggakan, '31_60')
            nol = self._spp(7, potongan=[(self.beasiswa, 150000)])
            self.assertEqual(nol.amount_total, 0)
            self.assertFalse(nol.nti_edu_umur_tunggakan)
            sept_b = self._spp(9, siswa=self.siswa_b)
            tunggakan = Move.search(Move._nti_edu_domain_tunggakan())
            self.assertIn(spp, tunggakan)
            self.assertIn(sept_b, tunggakan)  # 10 September sudah lewat
            self.assertNotIn(nol, tunggakan)
            # Bendahara melihat daftar tunggakan unitnya.
            self.assertIn(spp, Move.with_user(self.bendahara_smp).search(Move._nti_edu_domain_tunggakan()))

        with freeze_time('2026-09-10'):
            self.assertNotIn(sept_b, Move.search(Move._nti_edu_domain_tunggakan()))

        # Jadwal harian memperbarui umur.
        with freeze_time('2026-11-09'):
            self.Mesin._cron_perbarui_umur()
            self.assertEqual(spp.nti_edu_umur_tunggakan, '90_plus')
            self.assertEqual(sept_b.nti_edu_umur_tunggakan, '31_60')
        with freeze_time('2026-09-15'):
            self.Mesin._cron_perbarui_umur()
            self.assertEqual(sept_b.nti_edu_umur_tunggakan, '0_30')

        # Dilunasi → keluar dari tunggakan saat itu juga.
        with freeze_time('2026-09-24'):
            self.Mesin._bayar(spp, 150000, self.rekening_smp, date(2026, 9, 24), 'Lunas')
            self.assertFalse(spp.nti_edu_jatuh_tempo_terbuka)
            self.assertFalse(spp.nti_edu_umur_tunggakan)
            self.assertNotIn(spp, Move.search(Move._nti_edu_domain_tunggakan()))

        # Bercicil: jatuh tempo terbuka = cicilan terbuka paling awal, bukan jatuh tempo invoice.
        with freeze_time('2026-08-15'):
            pangkal = Move._nti_edu_terbitkan(
                self.siswa_b, self.pangkal, 1000000, date(2026, 7, 1), date(2026, 7, 10))
            pangkal._nti_edu_atur_cicilan(2)
            self.assertEqual(pangkal.invoice_date_due, date(2026, 8, 10))
            self.assertEqual(pangkal.nti_edu_jatuh_tempo_terbuka, date(2026, 7, 10))
            self.assertEqual(pangkal.nti_edu_umur_tunggakan, '31_60')
            self.Mesin._bayar(pangkal, 500000, self.rekening_smp, date(2026, 8, 15), 'Cicilan 1')
            self.assertEqual(pangkal.nti_edu_jatuh_tempo_terbuka, date(2026, 8, 10))
            self.assertEqual(pangkal.nti_edu_umur_tunggakan, '0_30')

    # --- email -------------------------------------------------------------------------------

    def test_pengingat(self):
        self.unit_smp.write({'nti_edu_pengingat_hari': 3, 'nti_edu_pengingat_tunggakan': 0})
        self.unit_sma.write({'nti_edu_pengingat_hari': 0})
        spp_a = self._spp(8)
        spp_b = self._spp(8, siswa=self.siswa_b)
        lain_hari = self._spp(9)

        self.Mesin._cron_pengingat(hari_ini=date(2026, 8, 6))
        self.assertFalse(self._email(self.wali_x, 'Pengingat'))

        self.Mesin._cron_pengingat(hari_ini=date(2026, 8, 7))
        email = self._email(self.wali_x, 'Pengingat')
        self.assertEqual(len(email), 1)
        self.assertIn(spp_a.name, email.body_html)
        self.assertNotIn(lain_hari.name, email.body_html)
        self.assertNotIn(spp_b.name, email.body_html)
        # Siswa tanpa wali ber-email: tidak ada email, tercatat di chatter tagihan.
        self.assertTrue(self._catatan(spp_b, 'Email tidak terkirim'))
        self.assertFalse(self._catatan(spp_a, 'Email tidak terkirim'))

        # Wali yang diarsipkan bukan penerima.
        ayah_b = self.env['res.partner'].create({'name': 'Ayah B Laporan', 'email': 'ayah.b.laporan@example.com'})
        self.env['nti_edu.siswa.wali'].create({
            'siswa_id': self.siswa_b.id, 'partner_id': ayah_b.id, 'hubungan': 'ayah', 'is_penanggung_biaya': True})
        self.assertEqual(self.siswa_b._nti_edu_penerima_tagihan(), ayah_b)
        self.assertEqual(
            (self.siswa_a | self.siswa_b)._nti_edu_peta_penerima_tagihan(),
            {self.siswa_a.id: self.wali_x, self.siswa_b.id: ayah_b})
        ayah_b.active = False
        self.assertFalse(self.siswa_b._nti_edu_penerima_tagihan())

        # Pengingat mati → tidak ada email.
        self.unit_smp.nti_edu_pengingat_hari = 0
        self.Mesin._cron_pengingat(hari_ini=date(2026, 9, 7))
        self.assertEqual(len(self._email(self.wali_x, 'Pengingat')), 1)

        # Ringkasan tunggakan tiap 7 hari, acuan tanggal 1 bulan berjalan.
        self.unit_smp.nti_edu_pengingat_tunggakan = 7
        self.Mesin._cron_pengingat(hari_ini=date(2026, 9, 2))
        self.assertFalse(self._email(self.wali_x, 'Tunggakan'))
        self.Mesin._cron_pengingat(hari_ini=date(2026, 9, 8))
        ringkasan = self._email(self.wali_x, 'Tunggakan')
        self.assertEqual(len(ringkasan), 1)
        self.assertIn(spp_a.name, ringkasan.body_html)
        self.assertNotIn(lain_hari.name, ringkasan.body_html)  # jatuh tempo 10 September belum lewat
        self.Mesin._cron_pengingat(hari_ini=date(2026, 10, 1))
        self.assertEqual(len(self._email(self.wali_x, 'Tunggakan')), 2)
        # Pengingat dan dua ringkasan berkala memuat spp_b, tetapi catatan "tidak terkirim" hanya sekali.
        self.assertEqual(len(self._catatan(spp_b, 'Email tidak terkirim')), 1)

        # Kirim Pengingat manual (Bendahara): satu email per penerima.
        tunggakan = spp_a | lain_hari | spp_b
        with self.assertRaises(AccessError):
            tunggakan.with_user(self.pemantau_smp).action_nti_edu_kirim_pengingat()
        with self.assertRaises(AccessError):
            tunggakan.with_user(self.bendahara_sma).action_nti_edu_kirim_pengingat()
        hasil = tunggakan.with_user(self.bendahara_smp).action_nti_edu_kirim_pengingat()
        self.assertEqual(hasil['tag'], 'display_notification')
        ringkasan = self._email(self.wali_x, 'Tunggakan')
        self.assertEqual(len(ringkasan), 3)
        terbaru = ringkasan.sorted('id')[-1]
        self.assertIn(spp_a.name, terbaru.body_html)
        self.assertIn(lain_hari.name, terbaru.body_html)

    def test_email_terbit_digest(self):
        adik = self._buat_siswa('Adik A Tagihan', self.unit_smp, 'TG009')
        self._masukkan(adik, self.rombel_8a)
        self.env['nti_edu.siswa.wali'].create({
            'siswa_id': adik.id, 'partner_id': self.wali_x.id, 'hubungan': 'ayah', 'is_penanggung_biaya': True})
        self.env['nti_edu.tagihan.skema'].create({
            'company_id': self.unit_smp.id, 'tahun_ajaran_id': self.ta.id, 'state': 'aktif',
            'baris_ids': [(0, 0, {'komponen_id': self.spp.id, 'nominal': 150000})]})
        self.unit_smp.write({
            'nti_edu_tagihan_mulai': date(2026, 7, 1), 'nti_edu_tagihan_otomatis': True,
            'nti_edu_email_tagihan_terbit': True})

        self.Mesin._cron_buat_tagihan(hari_ini=date(2026, 8, 1))
        tagihan = self.Move.search([('nti_edu_komponen_id', '=', self.spp.id)])
        self.assertEqual(len(tagihan), 6)  # Juli & Agustus untuk A, B, adik
        email = self._email(self.wali_x, 'Tagihan Baru')
        self.assertEqual(len(email), 1)
        for t in tagihan.filtered(lambda m: m.nti_edu_siswa_id in self.siswa_a | adik):
            self.assertIn(t.name, email.body_html)
        for t in tagihan.filtered(lambda m: m.nti_edu_siswa_id == self.siswa_b):
            self.assertNotIn(t.name, email.body_html)
            self.assertTrue(self._catatan(t, 'Email tidak terkirim'))

        # Jalan berikutnya tanpa tagihan baru tidak mengirim apa pun.
        self.Mesin._cron_buat_tagihan(hari_ini=date(2026, 8, 2))
        self.assertEqual(len(self._email(self.wali_x, 'Tagihan Baru')), 1)

        # Pengaturan mati → tidak ada email.
        self.unit_smp.nti_edu_email_tagihan_terbit = False
        self.Mesin._cron_buat_tagihan(hari_ini=date(2026, 9, 1))
        self.assertEqual(len(self.Move.search([('nti_edu_komponen_id', '=', self.spp.id)])), 9)
        self.assertEqual(len(self._email(self.wali_x, 'Tagihan Baru')), 1)

        # Wizard Buat Tagihan: satu email per penerima untuk satu jalan.
        self.unit_smp.nti_edu_email_tagihan_terbit = True
        wizard = self.env['nti_edu.tagihan.buat.wizard'].with_user(self.bendahara_smp).create({
            'company_id': self.unit_smp.id, 'komponen_id': self.spp.id, 'tahun_ajaran_id': self.ta.id,
            'periode': date(2026, 10, 1)})
        wizard.action_terbitkan()
        self.assertEqual(len(self._email(self.wali_x, 'Tagihan Baru')), 2)

    def test_email_terbit_lanjut_setelah_gagal(self):
        # Jadwal berhenti di tengah unit sesudah pekerjaan pertama di-commit: email tagihan pekerjaan itu tidak
        # hilang, melainkan dikirim di awal jalan berikutnya, tepat sekali.
        self.env['nti_edu.tagihan.skema'].create({
            'company_id': self.unit_smp.id, 'tahun_ajaran_id': self.ta.id, 'state': 'aktif',
            'baris_ids': [(0, 0, {'komponen_id': self.spp.id, 'nominal': 150000})]})
        self.unit_smp.write({
            'nti_edu_tagihan_mulai': date(2026, 7, 1), 'nti_edu_tagihan_otomatis': True,
            'nti_edu_email_tagihan_terbit': True})
        Mesin = type(self.Mesin)
        terbitkan_asli = Mesin._terbitkan
        panggilan = []

        def terbitkan_mati(self_mesin, *args, **kwargs):
            panggilan.append(args)
            if len(panggilan) == 2:
                raise psycopg2.OperationalError('Koneksi putus')
            return terbitkan_asli(self_mesin, *args, **kwargs)

        # Bukan assertRaises: savepoint-nya akan membatalkan pekerjaan yang (pura-pura) sudah di-commit.
        mati = False
        with patch('odoo.addons.nti_edu_tagihan.models.mesin._boleh_commit', return_value=True), \
                patch.object(self.env.cr, 'commit') as commit, patch.object(Mesin, '_terbitkan', terbitkan_mati):
            try:
                self.Mesin._cron_buat_tagihan(hari_ini=date(2026, 8, 1))
            except psycopg2.OperationalError:
                mati = True
        self.assertTrue(mati)
        self.assertEqual(commit.call_count, 1)
        juli = self.Move.search([('nti_edu_komponen_id', '=', self.spp.id)])
        self.assertEqual(set(juli.mapped('nti_edu_periode')), {date(2026, 7, 1)})
        self.assertTrue(all(juli.mapped('nti_edu_email_terbit_antre')))
        self.assertFalse(self._email(self.wali_x, 'Tagihan Baru'))

        self.Mesin._cron_buat_tagihan(hari_ini=date(2026, 8, 1))
        email = self._email(self.wali_x, 'Tagihan Baru')
        self.assertEqual(len(email), 2)  # antrean tertinggal (Juli), lalu tagihan baru jalan ini (Agustus)
        juli_a = juli.filtered(lambda m: m.nti_edu_siswa_id == self.siswa_a)
        self.assertEqual(len(email.filtered(lambda m: juli_a.name in m.body_html)), 1)
        semua = self.Move.search([('nti_edu_komponen_id', '=', self.spp.id)])
        self.assertEqual(len(semua), 4)
        self.assertFalse(any(semua.mapped('nti_edu_email_terbit_antre')))

        self.Mesin._cron_buat_tagihan(hari_ini=date(2026, 8, 2))
        self.assertEqual(len(self._email(self.wali_x, 'Tagihan Baru')), 2)

        # Pengaturan mati saat terbit: tagihan tidak masuk antrean.
        self.unit_smp.nti_edu_email_tagihan_terbit = False
        self.Mesin._cron_buat_tagihan(hari_ini=date(2026, 9, 1))
        september = self.Move.search([('nti_edu_periode', '=', date(2026, 9, 1))])
        self.assertTrue(september)
        self.assertFalse(any(september.mapped('nti_edu_email_terbit_antre')))

    # --- wali kelas --------------------------------------------------------------------------

    def test_menu_tunggakan_rombel(self):
        Menu = self.env['ir.ui.menu']
        akar = self.env.ref('nti_edu_tagihan.menu_tagihan_root')
        item = self.env.ref('nti_edu_tagihan.menu_tunggakan_rombel_saya')
        self.assertEqual(item.parent_id, self.env.ref('nti_edu_base.menu_data_sekolah'))
        terlihat_guru = Menu.with_user(self.user_guru_smp)._visible_menu_ids()
        self.assertNotIn(akar.id, terlihat_guru)
        self.assertIn(item.id, terlihat_guru)
        terlihat_pemantau = Menu.with_user(self.pemantau_smp)._visible_menu_ids()
        self.assertIn(akar.id, terlihat_pemantau)
        self.assertIn(item.id, terlihat_pemantau)

    def test_tunggakan_wali_kelas(self):
        Wali = self.env['nti_edu.tagihan.tunggakan.wali']
        guru = self.user_guru_smp
        guru_lain = new_test_user(
            self.env, login='tg_guru_lain', groups='nti_edu_base.group_base_pengguna',
            company_id=self.unit_smp.id, company_ids=[(6, 0, self.unit_smp.ids)])
        self.rombel_7a.wali_kelas_id = guru
        with freeze_time('2026-09-01'):
            spp_a = self._spp(8)
            self._spp(8, siswa=self.siswa_b)
            self.assertFalse(self.unit_smp.nti_edu_wali_kelas_lihat_tunggakan)
            hasil = Wali.with_user(guru).action_buka_tunggakan_rombel()
            self.assertEqual(hasil['tag'], 'display_notification')
            self.assertEqual(hasil['params']['type'], 'warning')

            self.unit_smp.nti_edu_wali_kelas_lihat_tunggakan = True
            hasil = Wali.with_user(guru).action_buka_tunggakan_rombel()
            self.assertEqual(hasil['type'], 'ir.actions.act_window')
            baris = Wali.with_user(guru).search(hasil['domain'])
            self.assertEqual(baris.mapped('siswa_nama'), [self.siswa_a.name])
            self.assertEqual(baris.rombel, self.rombel_7a.name)
            self.assertEqual(baris.komponen, self.spp.name)
            self.assertEqual(baris.sisa, spp_a.amount_residual)
            self.assertEqual(baris.jatuh_tempo, date(2026, 8, 10))
            # Baris milik guru lain tidak terlihat; guru tidak bisa mengubahnya.
            self.assertFalse(Wali.with_user(guru_lain).search([('id', 'in', baris.ids)]))
            with self.assertRaises(AccessError):
                baris.with_user(guru).write({'sisa': 0})

            hasil = Wali.with_user(guru_lain).action_buka_tunggakan_rombel()
            self.assertEqual(hasil['tag'], 'display_notification')
