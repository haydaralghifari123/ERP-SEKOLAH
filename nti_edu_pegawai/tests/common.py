# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, new_test_user


class NtiPegawaiCommon(TransactionCase):
    """Data dasar tes pegawai; tidak bergantung pada data demo."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['nti_edu.tahun.ajaran'].search([('is_aktif', '=', True)]).write({'is_aktif': False})
        Company = cls.env['res.company']
        cls.yayasan = Company.create({'name': 'Yayasan Pegawai Tes', 'nti_edu_jenis': 'yayasan'})
        cls.unit_smp = Company.create({
            'name': 'SMP Pegawai Tes', 'parent_id': cls.yayasan.id, 'nti_edu_jenis': 'unit',
            'nti_edu_jenjang_id': cls.env.ref('nti_edu_base.jenjang_smp').id, 'nti_edu_kode': 'pgsmp',
        })
        cls.unit_sma = Company.create({
            'name': 'SMA Pegawai Tes', 'parent_id': cls.yayasan.id, 'nti_edu_jenis': 'unit',
            'nti_edu_jenjang_id': cls.env.ref('nti_edu_base.jenjang_sma').id, 'nti_edu_kode': 'pgsma',
        })
        operator = 'nti_edu_pegawai.group_pegawai_operator'
        cls.tu_smp = cls._buat_user('peg_tu_smp', operator, cls.unit_smp)
        cls.tu_sma = cls._buat_user('peg_tu_sma', operator, cls.unit_sma)
        cls.tu_dua = cls._buat_user('peg_tu_dua', operator, cls.unit_smp | cls.unit_sma)
        cls.hrd = cls._buat_user('peg_hrd', 'nti_edu_pegawai.group_pegawai_hrd', cls.unit_smp | cls.unit_sma)
        cls.guru_smp = cls._buat_user('peg_guru_smp', 'nti_edu_base.group_base_pengguna', cls.unit_smp)

    @classmethod
    def _buat_user(cls, login, grup, units):
        return new_test_user(
            cls.env, login=login, groups=grup,
            company_id=units[0].id, company_ids=[(6, 0, units.ids)])

    @classmethod
    def _buat_pegawai(cls, nama, unit, **vals):
        """Buat pegawai (hr.employee) sebagai superuser; kontak kerja dibuat otomatis oleh hr."""
        return cls.env['hr.employee'].with_context(tracking_disable=True).create(
            dict(vals, name=nama, company_id=unit.id))
