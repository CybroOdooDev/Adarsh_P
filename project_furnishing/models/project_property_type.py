# -*- coding: utf-8 -*-
from odoo import models, fields


class ProjectPropertyType(models.Model):
    _name = 'project.property.type'
    _description = 'Project Property Type'
    _order = 'sequence, name'

    name = fields.Char(string='Property Type', required=True, translate=True)
    code = fields.Char(string='Code', size=20)
    sequence = fields.Integer(string='Sequence', default=10)
    description = fields.Text(string='Description / Notes')
    active = fields.Boolean(string='Active', default=True)
    project_count = fields.Integer(
        string='Projects Count',
        compute='_compute_project_count'
    )

    def _compute_project_count(self):
        project_data = self.env['project.project']._read_group(
            domain=[('property_type_id', 'in', self.ids)],
            groupby=['property_type_id'],
            aggregates=['__count']
        )
        data_map = {pt.id: count for pt, count in project_data}
        for record in self:
            record.project_count = data_map.get(record.id, 0)

    def action_view_projects(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'project.project',
            'view_mode': 'kanban,list,form',
            'views': [
                (self.env.ref('project_furnishing.view_project_furnishing_project_kanban').id, 'kanban'),
                (self.env.ref('project_furnishing.view_project_furnishing_project_list').id, 'list'),
                (self.env.ref('project_furnishing.view_project_furnishing_project_form').id, 'form'),
            ],
            'search_view_id': [self.env.ref('project_furnishing.view_project_furnishing_project_search').id, 'search'],
            'domain': [('property_type_id', '=', self.id)],
            'context': {'default_property_type_id': self.id, 'default_is_furnishing_project': True},
        }
