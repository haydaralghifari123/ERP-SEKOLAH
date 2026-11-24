# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, new_test_user


class NtiEduCommon(TransactionCase):
    """Data dasar bersama untuk tes NTI Edu; tidak bergantung pada data demo."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Data demo bisa memuat tahun ajaran aktif; nonaktifkan agar tidak bentrok dengan constraint "satu aktif".
        cls.env['nti_edu.tahun.ajaran'].search([('is_aktif', '=', True)]).write({'is_aktif': False})
        Company = cls.env['res.company']
        cls.yayasan = Company.create({'name': 'Yayasan Tes', 'nti_edu_jenis': 'yayasan'})
        cls.unit_smp = Company.create({
            'name': 'SMP Tes', 'parent_id': cls.yayasan.id, 'nti_edu_jenis': 'unit',
            'nti_edu_jenjang_id': cls.env.ref('nti_edu_base.jenjang_smp').id, 'nti_edu_kode': 'smpt',
        })
        cls.unit_sma = Company.create({
            'name': 'SMA Tes', 'parent_id': cls.yayasan.id, 'nti_edu_jenis': 'unit',
            'nti_edu_jenjang_id': cls.env.ref('nti_edu_base.jenjang_sma').id, 'nti_edu_kode': 'smat',
        })
        cls.user_operator_smp = cls._buat_user('tes_operator_smp', 'nti_edu_base.group_base_operator', cls.unit_smp)
        cls.user_guru_smp = cls._buat_user('tes_guru_smp', 'nti_edu_base.group_base_pengguna', cls.unit_smp)
        cls.user_guru_sma = cls._buat_user('tes_guru_sma', 'nti_edu_base.group_base_pengguna', cls.unit_sma)
        cls.user_eksternal = cls._buat_user('tes_eksternal', 'nti_edu_base.group_base_eksternal', cls.unit_smp)

    @classmethod
    def _buat_user(cls, login, grup, unit):
        return new_test_user(
            cls.env, login=login, groups=grup,
            company_id=unit.id, company_ids=[(6, 0, unit.ids)])

    @classmethod
    def _buat_siswa(cls, nama, unit, nis, **vals):
        """Buat siswa sebagai superuser (partner dengan nti_edu_is_siswa)."""
        return cls.env['res.partner'].create(dict(
            vals, name=nama, nti_edu_is_siswa=True, company_id=unit.id, nti_edu_nis=nis))
