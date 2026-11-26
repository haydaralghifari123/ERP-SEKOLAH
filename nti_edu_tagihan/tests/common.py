# -*- coding: utf-8 -*-
from datetime import date

from odoo.tests.common import new_test_user

from odoo.addons.nti_edu_base.tests.common import NtiEduCommon


class NtiTagihanCommon(NtiEduCommon):
    """Data dasar tes tagihan: bagan akun di yayasan, tahun ajaran, rombel, siswa, wali, dan user keuangan.

    Tidak bergantung pada data demo.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ref = cls.env.ref
        # Bagan akun dimuat di yayasan (root); unit adalah cabang yang memakai bagan akun yang sama.
        cls.env['account.chart.template'].try_loading('generic_coa', company=cls.yayasan, install_demo=False)

        cls.ta = cls.env['nti_edu.tahun.ajaran'].create({
            'name': '2026/2027', 'tanggal_mulai': date(2026, 7, 1), 'tanggal_selesai': date(2027, 6, 30),
            'is_aktif': True,
        })
        Semester = cls.env['nti_edu.semester']
        cls.semester_ganjil = Semester.create({
            'tahun_ajaran_id': cls.ta.id, 'jenis': 'ganjil',
            'tanggal_mulai': date(2026, 7, 1), 'tanggal_selesai': date(2026, 12, 31)})
        cls.semester_genap = Semester.create({
            'tahun_ajaran_id': cls.ta.id, 'jenis': 'genap',
            'tanggal_mulai': date(2027, 1, 1), 'tanggal_selesai': date(2027, 6, 30)})

        cls.rombel_7a = cls._buat_rombel('VII A', ref('nti_edu_base.tingkat_smp_7'), cls.unit_smp)
        cls.rombel_8a = cls._buat_rombel('VIII A', ref('nti_edu_base.tingkat_smp_8'), cls.unit_smp)
        cls.rombel_10a = cls._buat_rombel('X A', ref('nti_edu_base.tingkat_sma_10'), cls.unit_sma)

        cls.siswa_a = cls._buat_siswa('Siswa A Tagihan', cls.unit_smp, 'TG001')
        cls.siswa_b = cls._buat_siswa('Siswa B Tagihan', cls.unit_smp, 'TG002')
        cls.siswa_c = cls._buat_siswa('Siswa C Tagihan', cls.unit_sma, 'TG003')
        cls._masukkan(cls.siswa_a, cls.rombel_7a)
        cls._masukkan(cls.siswa_b, cls.rombel_8a)
        cls._masukkan(cls.siswa_c, cls.rombel_10a)

        # Wali portal yang sama untuk siswa A (SMP) dan siswa C (SMA): kakak-adik lintas unit.
        cls.user_wali_x = new_test_user(
            cls.env, login='tg_wali_x', groups='base.group_portal',
            name='Wali X Tagihan', email='wali.x.tagihan@example.com')
        cls.wali_x = cls.user_wali_x.partner_id
        SiswaWali = cls.env['nti_edu.siswa.wali']
        for siswa in (cls.siswa_a, cls.siswa_c):
            SiswaWali.create({
                'siswa_id': siswa.id, 'partner_id': cls.wali_x.id, 'hubungan': 'ayah',
                'is_kontak_utama': True, 'is_penanggung_biaya': True,
            })

        cls.bendahara_smp = cls._buat_user_keu(
            'tg_bendahara_smp', 'nti_edu_tagihan.group_tagihan_bendahara', cls.unit_smp)
        cls.bendahara_sma = cls._buat_user_keu(
            'tg_bendahara_sma', 'nti_edu_tagihan.group_tagihan_bendahara', cls.unit_sma)
        cls.pemantau_smp = cls._buat_user_keu(
            'tg_pemantau_smp', 'nti_edu_tagihan.group_tagihan_pemantau', cls.unit_smp)
        cls.admin_keu = cls._buat_user_keu(
            'tg_admin_keu', 'nti_edu_tagihan.group_tagihan_admin', cls.yayasan | cls.unit_smp | cls.unit_sma)
        cls.sysadmin = cls._buat_user_keu(
            'tg_sysadmin', 'base.group_system', cls.yayasan | cls.unit_smp | cls.unit_sma)

    @classmethod
    def _buat_rombel(cls, nama, tingkat, unit):
        return cls.env['nti_edu.rombel'].create({
            'name': nama, 'tahun_ajaran_id': cls.ta.id, 'tingkat_id': tingkat.id, 'company_id': unit.id})

    @classmethod
    def _masukkan(cls, siswa, rombel, tanggal_masuk=None):
        return cls.env['nti_edu.rombel.anggota'].create({
            'rombel_id': rombel.id, 'siswa_id': siswa.id,
            'tanggal_masuk': tanggal_masuk or rombel.tahun_ajaran_id.tanggal_mulai})

    @classmethod
    def _buat_user_keu(cls, login, grup, units):
        return new_test_user(
            cls.env, login=login, groups=grup,
            company_id=units[0].id, company_ids=[(6, 0, units.ids)])

    @classmethod
    def _buat_komponen(cls, nama, periode_xmlid, **vals):
        """Buat komponen biaya sebagai superuser; `periode_xmlid` = xmlid periode tanpa nama modul (atau None)."""
        if periode_xmlid:
            vals.setdefault('periode_jenis_id', cls.env.ref('nti_edu_tagihan.%s' % periode_xmlid).id)
        return cls.env['nti_edu.tagihan.komponen'].create(dict(vals, name=nama))

    @classmethod
    def _buat_rekening(cls, unit):
        """Rekening pembayaran khusus `unit`, dicatat di jurnal bank yayasan."""
        jurnal = cls.env['account.journal'].search([
            ('company_id', '=', cls.yayasan.id), ('type', '=', 'bank')], limit=1)
        return cls.env['nti_edu.tagihan.rekening'].create({
            'name': 'Rekening %s' % unit.name, 'bank': 'Bank Tes', 'nomor': '1234567890',
            'atas_nama': cls.yayasan.name, 'company_ids': [(6, 0, unit.ids)], 'journal_id': jurnal.id,
        })
