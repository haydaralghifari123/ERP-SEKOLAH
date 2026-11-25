# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from ..models.res_partner import GRUP_HRD, GRUP_OPERATOR


class PenempatanWizard(models.TransientModel):
    _name = 'nti_edu.pegawai.penempatan.wizard'
    _description = 'Wizard Tempatkan Pegawai di Unit Lain'

    employee_id = fields.Many2one('hr.employee', string='Pegawai', required=True)
    company_id = fields.Many2one('res.company', string='Unit Tujuan', required=True)
    company_ids_diizinkan = fields.Many2many(
        'res.company', compute='_compute_company_ids_diizinkan', string='Unit yang Boleh Dipilih')
    nti_edu_jenis_ptk = fields.Selection(
        selection=lambda self: self.env['hr.employee']._fields['nti_edu_jenis_ptk'].selection,
        string='Jenis PTK')
    nti_edu_tmt = fields.Date(string='TMT di Unit Tujuan')

    def _unit_tujuan_boleh(self, pegawai):
        """Unit tujuan yang boleh dipilih pemanggil untuk pegawai ini (tanpa unit yang sudah aktif)."""
        Company = self.env['res.company'].sudo()
        kontak = pegawai.sudo().work_contact_id
        if not kontak:
            return Company
        semua = self.env['hr.employee'].sudo().with_context(active_test=False).search(
            [('work_contact_id', '=', kontak.id)])
        aktif = semua.filtered('active').company_id
        asal = semua.company_id
        if self.env.su:
            unit = Company.search([
                ('nti_edu_jenis', '=', 'unit'), ('parent_id', 'in', asal.parent_id.ids)])
        else:
            pemegang = self.env.user.company_ids.sudo()
            if self.env.user.has_group(GRUP_HRD):
                unit = pemegang.filtered(
                    lambda c: c.nti_edu_jenis == 'unit' and c.parent_id in asal.parent_id)
            elif asal <= pemegang:
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
        if tujuan.nti_edu_jenis != 'unit':
            raise UserError(_("Unit tujuan harus berupa unit sekolah, bukan yayasan."))

        Pegawai = self.env['hr.employee'].sudo().with_context(active_test=False)
        semua = Pegawai.search([('work_contact_id', '=', kontak.id)])
        # Hak dicek dengan hak pemanggil sebelum sudo apa pun.
        if not self.env.su:
            asal = semua.company_id
            if tujuan not in pemanggil.company_ids:
                raise AccessError(_("Penempatan hanya boleh ke unit yang Anda pegang."))
            if pemanggil.has_group(GRUP_HRD):
                if tujuan.parent_id != asal.parent_id:
                    raise AccessError(_("Unit tujuan harus berada di yayasan yang sama dengan unit asal."))
            elif not asal <= pemanggil.company_ids:
                raise AccessError(_("Penempatan hanya boleh oleh HRD atau TU yang memegang unit asal."))

        if semua.filtered(lambda p: p.active and p.company_id == tujuan):
            raise UserError(_("%s sudah aktif di unit tujuan.", pegawai.name))

        nilai = {}
        if self.nti_edu_jenis_ptk:
            nilai['nti_edu_jenis_ptk'] = self.nti_edu_jenis_ptk
        if self.nti_edu_tmt:
            nilai['nti_edu_tmt'] = self.nti_edu_tmt
        user = semua.user_id[:1]
        arsip = semua.filtered(lambda p: p.company_id == tujuan and not p.active)
        if arsip:
            hasil = arsip[0]
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
        if user and tujuan not in user.company_ids:
            user.sudo().write({'company_ids': [(4, tujuan.id)]})
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
