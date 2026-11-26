# -*- coding: utf-8 -*-
from datetime import date
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import freeze_time, tagged
from odoo.tools import mute_logger

from .common import NtiTagihanCommon

LOGGER_MESIN = 'odoo.addons.nti_edu_tagihan.models.mesin'


@tagged('post_install', '-at_install')
class TestDenda(NtiTagihanCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ref = cls.env.ref
        cls.Move = cls.env['account.move']
        cls.Mesin = cls.env['nti_edu.tagihan.mesin']
        cls.Wizard = cls.env['nti_edu.tagihan.hapus.denda.wizard']
        Aturan = cls.env['nti_edu.tagihan.aturan.denda']
        cls.komponen_denda = cls._buat_komponen('Denda Tes', None, jenis='denda')
        cls.aturan_bulan = Aturan.create({
            'name': 'Denda 10rb per bulan tenggang 7', 'tipe': 'tetap', 'nilai': 10000, 'berulang': 'per_bulan',
            'tenggang_hari': 7, 'komponen_denda_id': cls.komponen_denda.id})
        cls.spp = cls._buat_komponen('SPP Denda', 'periode_bulanan', aturan_denda_id=cls.aturan_bulan.id)
        cls.rekening_smp = cls._buat_rekening(cls.unit_smp)
        cls.alasan_kebijakan = ref('nti_edu_tagihan.alasan_hapus_kebijakan')
        cls.alasan_lainnya = ref('nti_edu_tagihan.alasan_hapus_lainnya')

    # --- bantuan ---------------------------------------------------------------------------

    def _terbitkan(self, komponen=None, siswa=None, nominal=150000, jatuh_tempo=date(2026, 8, 10),
                   periode=date(2026, 8, 1), **sekolah):
        komponen = komponen or self.spp
        if komponen.periode_jenis_id and komponen.periode_jenis_id.dasar != 'sekali':
            sekolah['periode'] = periode
        return self.Move._nti_edu_terbitkan(
            siswa or self.siswa_a, komponen, nominal, jatuh_tempo.replace(day=1), jatuh_tempo, **sekolah)

    def _denda(self, asal, semua=False):
        domain = [('move_type', '=', 'out_invoice'), ('nti_edu_tagihan_asal_id', '=', asal.id)]
        if not semua:
            domain.append(('state', '!=', 'cancel'))
        return self.Move.search(domain, order='nti_edu_denda_jatuh_tempo, nti_edu_denda_bulan_ke')

    def _cron(self, tanggal):
        with freeze_time(tanggal):
            self.Mesin._cron_denda()

    def _hapus(self, user, denda, alasan=None, catatan=False):
        wizard = self.Wizard.with_user(user).with_context(
            active_model='account.move', active_ids=denda.ids).create({
                'alasan_id': (alasan or self.alasan_kebijakan).id, 'catatan': catatan})
        self.assertEqual(wizard.tagihan_ids, denda)
        return wizard.action_hapus()

    # --- penerbitan --------------------------------------------------------------------------

    def test_per_bulan_tenggang(self):
        asal = self._terbitkan()
        self._cron('2026-08-17')
        self.assertFalse(self._denda(asal))

        self._cron('2026-08-18')
        denda = self._denda(asal)
        self.assertEqual(len(denda), 1)
        self.assertEqual(denda.state, 'posted')
        self.assertEqual(denda.amount_total, 10000)
        self.assertEqual(denda.nti_edu_komponen_id, self.komponen_denda)
        self.assertEqual(denda.nti_edu_siswa_id, self.siswa_a)
        self.assertEqual(denda.nti_edu_denda_jatuh_tempo, date(2026, 8, 10))
        self.assertEqual(denda.nti_edu_denda_bulan_ke, 1)
        self.assertEqual(denda.invoice_date, date(2026, 8, 18))
        self.assertEqual(denda.invoice_date_due, date(2026, 8, 18))

        # Cron sempat mati: semua bulan yang terlewat dikejar sekaligus.
        self._cron('2026-10-18')
        denda = self._denda(asal)
        self.assertEqual(denda.mapped('nti_edu_denda_bulan_ke'), [1, 2, 3])
        self.assertEqual(denda.mapped('amount_total'), [10000, 10000, 10000])
        self._cron('2026-10-18')
        self.assertEqual(len(self._denda(asal)), 3)

        # Denda itu sendiri tidak pernah didenda.
        self.assertFalse(self.Move.search([('nti_edu_tagihan_asal_id', 'in', denda.ids)]))

    def test_sekali_dan_persen(self):
        aturan = self.env['nti_edu.tagihan.aturan.denda'].create({
            'name': 'Denda 2 persen sekali', 'tipe': 'persen', 'nilai': 2, 'berulang': 'sekali',
            'komponen_denda_id': self.komponen_denda.id})
        pangkal = self._buat_komponen('Pangkal Denda', 'periode_sekali', aturan_denda_id=aturan.id)
        asal = self._terbitkan(komponen=pangkal, nominal=200000)
        self.Mesin._bayar(asal, 50000, self.rekening_smp, date(2026, 8, 5), 'Sebagian')
        self.assertEqual(asal.amount_residual, 150000)

        self._cron('2026-08-10')
        self.assertFalse(self._denda(asal))
        self._cron('2026-08-11')
        denda = self._denda(asal)
        self.assertEqual(len(denda), 1)
        self.assertEqual(denda.amount_total, 3000)
        self._cron('2026-12-11')
        self.assertEqual(self._denda(asal), denda)

    def test_persen_dibulatkan_rupiah(self):
        aturan = self.env['nti_edu.tagihan.aturan.denda'].create({
            'name': 'Denda 1,5 persen sekali', 'tipe': 'persen', 'nilai': 1.5, 'berulang': 'sekali',
            'komponen_denda_id': self.komponen_denda.id})
        self.spp.aturan_denda_id = aturan
        asal = self._terbitkan(nominal=123457)
        self._cron('2026-08-11')
        # 1,5% × 123.457 = 1.851,855 → 1.852
        self.assertEqual(self._denda(asal).amount_total, 1852)

    def test_maks(self):
        self.aturan_bulan.write({'tenggang_hari': 0, 'maks': 25000})
        asal = self._terbitkan()
        self._cron('2026-08-11')
        self._cron('2026-09-11')
        self._cron('2026-10-11')
        self.assertEqual(self._denda(asal).mapped('amount_total'), [10000, 10000, 5000])
        self._cron('2026-11-11')
        self._cron('2027-01-11')
        self.assertEqual(self._denda(asal).mapped('amount_total'), [10000, 10000, 5000])

        # Kejar ketinggalan sekaligus juga berhenti di batas.
        lain = self._terbitkan(siswa=self.siswa_b)
        self._cron('2027-01-11')
        self.assertEqual(self._denda(lain).mapped('amount_total'), [10000, 10000, 5000])

    def test_cicilan(self):
        aturan_cicil = self.env['nti_edu.tagihan.aturan.cicilan'].create({
            'name': 'Cicil 4x Denda', 'maks_kali': 4, 'jarak': 1, 'jarak_satuan': 'bulan'})
        aturan = self.env['nti_edu.tagihan.aturan.denda'].create({
            'name': 'Denda 2 persen per cicilan', 'tipe': 'persen', 'nilai': 2, 'berulang': 'sekali',
            'komponen_denda_id': self.komponen_denda.id})
        pangkal = self._buat_komponen(
            'Pangkal Cicil Denda', 'periode_sekali', aturan_denda_id=aturan.id, aturan_cicilan_id=aturan_cicil.id)
        asal = self._terbitkan(komponen=pangkal, nominal=1000000, jatuh_tempo=date(2026, 7, 10))
        asal._nti_edu_atur_cicilan(4)
        # Setelah dicicil, jatuh tempo invoice = cicilan terakhir; denda tetap menurut tiap cicilan.
        self.assertEqual(asal.invoice_date_due, date(2026, 10, 10))

        self._cron('2026-08-15')
        denda = self._denda(asal)
        self.assertEqual(denda.mapped('nti_edu_denda_jatuh_tempo'), [date(2026, 7, 10), date(2026, 8, 10)])
        self.assertEqual(denda.mapped('nti_edu_denda_bulan_ke'), [1, 1])
        # 2% dari sisa cicilan (250.000), bukan dari sisa tagihan.
        self.assertEqual(denda.mapped('amount_total'), [5000, 5000])
        self._cron('2026-08-15')
        self.assertEqual(len(self._denda(asal)), 2)
        self._cron('2026-09-11')
        self.assertEqual(self._denda(asal).mapped('nti_edu_denda_jatuh_tempo'),
                         [date(2026, 7, 10), date(2026, 8, 10), date(2026, 9, 10)])

    def test_tidak_denda(self):
        # Lunas.
        lunas = self._terbitkan(periode=date(2026, 7, 1), jatuh_tempo=date(2026, 7, 10))
        self.Mesin._bayar(lunas, 150000, self.rekening_smp, date(2026, 7, 5), 'Lunas')
        # Tagihan denda itu sendiri, walaupun komponen dendanya diberi aturan denda.
        self.komponen_denda.aturan_denda_id = self.aturan_bulan
        denda_manual = self._terbitkan(
            komponen=self.komponen_denda, siswa=self.siswa_b, nominal=10000)
        # Tagihan nol (beasiswa 100%).
        jenis = self.env['nti_edu.tagihan.potongan.jenis'].create({
            'name': 'Beasiswa Penuh Denda', 'tipe': 'persen', 'nilai_bawaan': 100,
            'komponen_ids': [(6, 0, self.spp.ids)]})
        nol = self.Move._nti_edu_terbitkan(
            self.siswa_a, self.spp, 150000, date(2026, 8, 1), date(2026, 8, 10), potongan=[(jenis, 150000)],
            periode=date(2026, 8, 1))
        self.assertEqual(nol.amount_total, 0)
        # Saldo awal dengan pengaturan denda saldo awal mati (bawaan).
        saldo_awal = self._terbitkan(periode=date(2026, 6, 1), jatuh_tempo=date(2026, 6, 10), saldo_awal=True)
        # Jatuh tempo sebelum Tagihan Mulai.
        self.unit_smp.nti_edu_tagihan_mulai = date(2026, 9, 1)
        sebelum_mulai = self._terbitkan(siswa=self.siswa_b, periode=date(2026, 8, 1), jatuh_tempo=date(2026, 8, 31))
        sesudah_mulai = self._terbitkan(siswa=self.siswa_b, periode=date(2026, 9, 1), jatuh_tempo=date(2026, 9, 1))

        self._cron('2026-12-20')
        for tagihan in (lunas, denda_manual, nol, saldo_awal, sebelum_mulai):
            self.assertFalse(self._denda(tagihan, semua=True), tagihan.name)
        self.assertFalse(self.Move.search([('nti_edu_tagihan_asal_id', '=', denda_manual.id)]))
        # Pembanding: tagihan sesudah Tagihan Mulai didenda.
        self.assertEqual(len(self._denda(sesudah_mulai)), 4)

        # Saldo awal didenda bila pengaturan unit menyala.
        self.unit_smp.nti_edu_denda_saldo_awal = True
        self.unit_smp.nti_edu_tagihan_mulai = False
        self._cron('2026-12-20')
        self.assertEqual(len(self._denda(saldo_awal)), 7)

    def test_cron_terdaftar_dan_commit(self):
        cron = self.env.ref('nti_edu_tagihan.cron_denda')
        self.assertTrue(cron.active)
        self.assertEqual(cron.code.strip(), 'model._cron_denda()')
        self.assertEqual((cron.interval_number, cron.interval_type), (1, 'days'))

        a = self._terbitkan()
        b = self._terbitkan(siswa=self.siswa_b)
        # Jalur cron sungguhan commit setelah tiap tagihan asal; di tes `_boleh_commit` palsu.
        with patch('odoo.addons.nti_edu_tagihan.models.mesin._boleh_commit', return_value=True), \
                patch.object(self.env.cr, 'commit') as commit:
            self.Mesin._cron_denda(hari_ini=date(2026, 8, 18))
        self.assertGreaterEqual(commit.call_count, 2)
        self.assertEqual(len(self._denda(a)), 1)
        self.assertEqual(len(self._denda(b)), 1)
        with patch.object(self.env.cr, 'commit') as commit:
            self.Mesin._cron_denda(hari_ini=date(2026, 9, 18))
        commit.assert_not_called()

    def test_galat_satu_tagihan_tidak_menghentikan(self):
        a = self._terbitkan()
        b = self._terbitkan(siswa=self.siswa_b)
        Mesin = type(self.Mesin)
        asli = Mesin._denda_tagihan

        def rusak(mesin, asal, hari_ini):
            if asal == a:
                raise ValueError('rusak')
            return asli(mesin, asal, hari_ini)

        with patch.object(Mesin, '_denda_tagihan', rusak), mute_logger(LOGGER_MESIN):
            self.Mesin._cron_denda(hari_ini=date(2026, 8, 18))
        self.assertFalse(self._denda(a))
        self.assertEqual(len(self._denda(b)), 1)

    # --- hapus denda ---------------------------------------------------------------------------

    def test_hapus_denda(self):
        self.assertTrue(self.unit_smp.nti_edu_denda_hapus_perlu_admin)
        asal = self._terbitkan()
        self._cron('2026-08-18')
        denda_1 = self._denda(asal)
        self.assertEqual(len(denda_1), 1)

        # Bawaan: hanya Admin Keuangan.
        with self.assertRaises(AccessError):
            self._hapus(self.bendahara_smp, denda_1)
        self.assertEqual(denda_1.state, 'posted')
        # Alasan yang mewajibkan catatan.
        with self.assertRaises(UserError):
            self._hapus(self.admin_keu, denda_1, alasan=self.alasan_lainnya)
        self.assertEqual(denda_1.state, 'posted')
        # Bukan tagihan denda.
        with self.assertRaises(UserError):
            self._hapus(self.admin_keu, asal)
        self.assertEqual(asal.state, 'posted')
        # Denda tidak bisa dibatalkan lewat pembatalan biasa (melewati aturan hapus denda).
        with self.assertRaises(UserError):
            denda_1.with_user(self.bendahara_smp)._nti_edu_batalkan('Salah')
        self.assertEqual(denda_1.state, 'posted')

        self._hapus(self.admin_keu, denda_1, alasan=self.alasan_lainnya, catatan='Keringanan rapat komite')
        self.assertEqual(denda_1.state, 'cancel')
        pesan = denda_1.message_ids.filtered(lambda m: 'Denda dihapus' in (m.body or ''))
        self.assertEqual(len(pesan), 1)
        self.assertIn('Lainnya', pesan.body)
        self.assertIn('Keringanan rapat komite', pesan.body)
        self.assertEqual(pesan.author_id, self.admin_keu.partner_id)
        # Denda yang dihapus tidak diterbitkan ulang oleh jadwal.
        self._cron('2026-08-18')
        self.assertFalse(self._denda(asal))
        self.assertEqual(self._denda(asal, semua=True), denda_1)

        # Pengaturan mati: Bendahara unit itu boleh, unit lain tidak.
        self.unit_smp.nti_edu_denda_hapus_perlu_admin = False
        self._cron('2026-09-18')
        denda_2 = self._denda(asal)
        self.assertEqual(denda_2.nti_edu_denda_bulan_ke, 2)
        with self.assertRaises(AccessError):
            self._hapus(self.bendahara_sma, denda_2)
        with self.assertRaises(AccessError):
            self._hapus(self.pemantau_smp, denda_2)
        self._hapus(self.bendahara_smp, denda_2)
        self.assertEqual(denda_2.state, 'cancel')
        self.assertEqual(denda_2.message_ids[0].author_id, self.bendahara_smp.partner_id)

        # Denda yang sudah dibayar tidak dapat dihapus.
        self._cron('2026-10-18')
        denda_3 = self._denda(asal)
        self.assertEqual(denda_3.nti_edu_denda_bulan_ke, 3)
        self.Mesin._bayar(denda_3, 4000, self.rekening_smp, date(2026, 10, 18), 'Sebagian denda')
        with self.assertRaises(UserError):
            self._hapus(self.admin_keu, denda_3)
        self.assertEqual(denda_3.state, 'posted')
