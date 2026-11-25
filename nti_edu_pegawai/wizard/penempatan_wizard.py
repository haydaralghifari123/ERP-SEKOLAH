# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from ..models.res_partner import GRUP_HRD, GRUP_OPERATOR


class PenempatanWizard(models.TransientModel):
    _name = 'nti_edu.pegawai.penempatan.wizard'
    _description = 'Wizard Tempatkan Pegawai di Unit Lain'

    employee_id = fields.Many2one('hr.employee', string='Pegawai', required=True)
    company_id = fields.Many2one(
        'res.company', string='Unit/Yayasan Tujuan', required=True,
        help='Unit sekolah tujuan; HRD juga dapat memilih yayasan yang sama dengan penempatan asal.')
    company_ids_diizinkan = fields.Many2many(
        'res.company', compute='_compute_company_ids_diizinkan', string='Unit/Yayasan yang Boleh Dipilih')
    nti_edu_jenis_ptk = fields.Selection(
        selection=lambda self: self.env['hr.employee']._fields['nti_edu_jenis_ptk'].selection,
        string='Jenis PTK')
    nti_edu_tmt = fields.Date(string='TMT di Unit/Yayasan Tujuan')

    @api.model
    def _yayasan_induk(self, companies):
        """Yayasan tempat `companies` bernaung: induk unit-unitnya, ditambah yayasan itu sendiri (staf yayasan)."""
        return (companies.filtered(lambda c: c.nti_edu_jenis == 'unit').parent_id
                | companies.filtered(lambda c: c.nti_edu_jenis == 'yayasan'))

    def _unit_tujuan_boleh(self, pegawai):
        """Unit (dan bagi HRD, yayasan) tujuan yang boleh dipilih pemanggil untuk pegawai ini, tanpa yang sudah
        aktif. HRD: unit dan yayasan di yayasan yang sama dengan penempatan asal; TU: unit yang ia pegang, tidak
        pernah yayasan, dan tidak untuk orang yang punya penempatan yayasan."""
        Company = self.env['res.company'].sudo()
        kontak = pegawai.sudo().work_contact_id
        if not kontak:
            return Company
        semua = self.env['hr.employee'].sudo().with_context(active_test=False).search(
            [('work_contact_id', '=', kontak.id)])
        aktif = semua.filtered('active').company_id
        asal = semua.company_id
        induk = self._yayasan_induk(asal)

        def se_yayasan(c):
            return (c.nti_edu_jenis == 'unit' and c.parent_id in induk) or (
                c.nti_edu_jenis == 'yayasan' and c in induk)

        if self.env.su:
            unit = Company.search([('nti_edu_jenis', 'in', ('unit', 'yayasan'))]).filtered(se_yayasan)
        else:
            pemegang = self.env.user.company_ids.sudo()
            if self.env.user.has_group(GRUP_HRD):
                unit = pemegang.filtered(se_yayasan)
            elif asal <= pemegang and not any(c.nti_edu_jenis == 'yayasan' for c in asal):
                unit = pemegang.filtered(lambda c: c.nti_edu_jenis == 'unit')
            else:
                return Company
        return unit - aktif

    @api.depends('employee_id')
    def _compute_company_ids_diizinkan(self):
        for rec in self:
            rec.company_ids_diizinkan = rec._unit_tujuan_boleh(rec.employee_id) if rec.employee_id else False

    def action_tempatkan(self):
        self.ensure_one()
        pemanggil = self.env.user
        if not (self.env.su or pemanggil.has_group(GRUP_OPERATOR) or pemanggil.has_group(GRUP_HRD)):
            raise AccessError(_("Hanya TU Pegawai atau HRD yang boleh menempatkan pegawai di unit lain."))
        pegawai = self.employee_id.sudo()
        kontak = pegawai.work_contact_id
        tujuan = self.company_id.sudo()
        if not kontak:
            raise UserError(_("Pegawai ini belum punya kontak kerja."))
        if tujuan.nti_edu_jenis not in ('unit', 'yayasan'):
            raise UserError(_("Tujuan penempatan harus unit sekolah atau yayasan."))

        Pegawai = self.env['hr.employee'].sudo().with_context(active_test=False)
        semua = Pegawai.search([('work_contact_id', '=', kontak.id)])
        # Hak dicek dengan hak pemanggil sebelum sudo apa pun.
        if not self.env.su:
            asal = semua.company_id
            if tujuan not in pemanggil.company_ids:
                raise AccessError(_("Penempatan hanya boleh ke unit/yayasan yang Anda pegang."))
            if pemanggil.has_group(GRUP_HRD):
                # Yayasan tujuan = tujuan itu sendiri (staf yayasan) atau induk unit tujuan.
                yayasan_tujuan = tujuan if tujuan.nti_edu_jenis == 'yayasan' else tujuan.parent_id
                if yayasan_tujuan != self._yayasan_induk(asal):
                    raise AccessError(_(
                        "Unit/yayasan tujuan harus berada di yayasan yang sama dengan penempatan asal."))
            elif not asal <= pemanggil.company_ids:
                raise AccessError(_("Penempatan hanya boleh oleh HRD atau TU yang memegang unit asal."))
            else:
                # Ke atau dari yayasan hanya HRD; dicek setelah TU terbukti memegang semua penempatan asal.
                self.env['hr.employee']._nti_edu_cek_yayasan(tujuan | asal)

        # Kontak siswa tidak pernah jadi kontak kerja (ditolak saat menautkan); jangan sampai dilepas dari unitnya.
        if kontak.nti_edu_is_siswa:
            raise UserError(_("Kontak siswa tidak boleh dipakai sebagai kontak kerja pegawai."))
        if semua.filtered(lambda p: p.active and p.company_id == tujuan):
            raise UserError(_("%s sudah aktif di unit tujuan.", pegawai.name))

        # Akses akun diatur di bawah dengan hak pemanggil, bukan otomatis oleh tulis sudo ini.
        Pegawai = Pegawai.with_context(nti_edu_tanpa_sinkron_akun=True)
        nilai = {}
        if self.nti_edu_jenis_ptk:
            nilai['nti_edu_jenis_ptk'] = self.nti_edu_jenis_ptk
        if self.nti_edu_tmt:
            nilai['nti_edu_tmt'] = self.nti_edu_tmt
        user = semua.user_id[:1]
        arsip = semua.filtered(lambda p: p.company_id == tujuan and not p.active)
        if arsip:
            hasil = arsip[0].with_env(Pegawai.env)
            nilai['active'] = True
            if user and not hasil.user_id:
                nilai['user_id'] = user.id
            hasil.write(nilai)
        else:
            nilai.update(name=pegawai.name, company_id=tujuan.id, work_contact_id=kontak.id)
            if user:
                nilai['user_id'] = user.id
            hasil = Pegawai.create(nilai)
        user = hasil.user_id
        if user and user.active:
            # Aturan wewenang yang sama dengan arsip/aktif lagi (akun HRD hanya oleh HRD, admin tidak disentuh).
            self.env['hr.employee']._nti_edu_atur_akses_akun(user, tambah=tujuan)
        # Kontak dipakai bersama: dilepas dari satu unit agar terbaca di semua unit.
        if kontak.company_id:
            kontak.write({'company_id': False})
        return {
            'type': 'ir.actions.act_window',
            'name': _("Pegawai"),
            'res_model': 'hr.employee',
            'res_id': hasil.id,
            'view_mode': 'form',
            'views': [(self.env.ref('nti_edu_pegawai.view_pegawai_form').id, 'form')],
            'target': 'current',
            'context': {'allowed_company_ids': pemanggil.company_ids.ids},
        }
