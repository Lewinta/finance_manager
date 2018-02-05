# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from frappe import _

def execute(filters=None):
	return get_columns(), get_data(filters)

def get_columns():
	return [
		{
			"label": _("Loan"),
			"fieldtype": "Link",
			"fieldname": "loan",
			"options": "Loan",
			"width": 100
		},
		{
			"label": _("Customer Name"),
			"fieldtype": "Data",
			"fieldname": "customer_name",
			"width": 300
		},
		{
			"label": _("Fecha de Pago"),
			"fieldtype": "Date",
			"fieldname": "date",
			"width": 120
		},
		{
			"label": _("Monto a Pagar"),
			"fieldtype": "Currency",
			"fieldname": "pending_amount",
			"width": 120
		},
		{
			"label": _("Monto Pagado"),
			"fieldtype": "Currency",
			"fieldname": "paid_amount",
			"width": 120
		},
		{
			"label": _("Estado"),
			"fieldtype": "Data",
			"fieldname": "status",
			"width": 100
		},
	]

def get_data(filters=None):
	conditions = get_conditions(filters)

	return frappe.db.sql("""
		SELECT 
			parent.name,
			parent.customer_name,
			child.fecha,
			child.monto_pendiente,
			child.monto_pagado,
			child.estado
		FROM `tabLoan` AS parent
		JOIN `tabTabla Amortizacion` AS child ON parent.name = child.parent
		WHERE 
			{conditions}
		ORDER BY fecha""".format(conditions=conditions),
	filters, as_list=True)

def get_conditions(filters=None):
	conditions = []

	if not filters.get("year") or not filters.get("month"):
		frappe.throw("Formato de fecha incompleto")

	if filters.get("status"):
		conditions.append("child.estado = %(status)s")

	if filters.get("company"):
		conditions.append("parent.company = %(company)s")

	conditions.append("DATE_FORMAT(child.fecha, '%%Y%%m') = '{year}{month}'".format(**filters))

	return " AND ".join(conditions)