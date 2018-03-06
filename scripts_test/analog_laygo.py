# -*- coding: utf-8 -*-

from typing import Dict, Any, Set

import yaml

from bag.core import BagProject
from bag.layout.routing import RoutingGrid, TrackManager
from bag.layout.template import TemplateDB

from abs_templates_ec.laygo.core import LaygoBase

from serdes_ec.layout.analog.qdr.base import HybridQDRBaseInfo, HybridQDRBase


class IntegAmp(HybridQDRBase):
    """An integrating amplifier.

    Parameters
    ----------
    temp_db : TemplateDB
            the template database.
    lib_name : str
        the layout library name.
    params : Dict[str, Any]
        the parameter values.
    used_names : Set[str]
        a set of already used cell names.
    **kwargs
        dictionary of optional parameters.  See documentation of
        :class:`bag.layout.template.TemplateBase` for details.
    """

    def __init__(self, temp_db, lib_name, params, used_names, **kwargs):
        # type: (TemplateDB, str, Dict[str, Any], Set[str], **kwargs) -> None
        HybridQDRBase.__init__(self, temp_db, lib_name, params, used_names, **kwargs)
        self._sch_params = None

    @property
    def sch_params(self):
        # type: () -> Dict[str, Any]
        return self._sch_params

    @classmethod
    def get_default_param_values(cls):
        # type: () -> Dict[str, Any]
        return dict(
            guard_ring_nf=0,
            top_layer=None,
            show_pins=True,
            options=None,
        )

    @classmethod
    def get_params_info(cls):
        # type: () -> Dict[str, str]
        return dict(
            lch='channel length, in meters.',
            ptap_w='NMOS substrate width, in meters/number of fins.',
            ntap_w='PMOS substrate width, in meters/number of fins.',
            w_dict='NMOS/PMOS width dictionary.',
            th_dict='NMOS/PMOS threshold flavor dictionary.',
            seg_dict='NMOS/PMOS number of segments dictionary.',
            fg_dum='Number of single-sided edge dummy fingers.',
            guard_ring_nf='Width of the guard ring, in number of fingers. 0 to disable.',
            top_layer='the top routing layer.',
            tr_widths='Track width dictionary.',
            tr_spaces='Track spacing dictionary.',
            show_pins='True to create pin labels.',
            options='AnalogBase options',
        )

    def draw_layout(self):
        lch = self.params['lch']
        ptap_w = self.params['ptap_w']
        ntap_w = self.params['ntap_w']
        w_dict = self.params['w_dict']
        th_dict = self.params['th_dict']
        seg_dict = self.params['seg_dict']
        fg_dum = self.params['fg_dum']
        guard_ring_nf = self.params['guard_ring_nf']
        top_layer = self.params['top_layer']
        tr_widths = self.params['tr_widths']
        tr_spaces = self.params['tr_spaces']
        show_pins = self.params['show_pins']
        options = self.params['options']

        if options is None:
            options = {}

        # get track manager and wire names
        tr_manager = TrackManager(self.grid, tr_widths, tr_spaces)
        wire_names = {
            'tail': dict(g=['clk', 'clk'], ds=['ntail']),
            'nen': dict(g=['en', 'en', 'en'], ds=['ntail']),
            'in': dict(g=['in', 'in'], ds=[]),
            'pen': dict(ds=['out', 'out'], g=['en', 'en', 'en']),
            'load': dict(ds=['ptail'], g=['clk', 'clk']),
        }

        # get total number of fingers
        qdr_info = HybridQDRBaseInfo(self.grid, lch, guard_ring_nf, top_layer=top_layer, **options)
        amp_info = qdr_info.get_integ_amp_info(seg_dict, fg_dum=fg_dum)
        fg_tot = amp_info['fg_tot']

        self.draw_rows(lch, fg_tot, ptap_w, ntap_w, w_dict, th_dict, tr_manager,
                       wire_names, top_layer=top_layer, **options)

        # draw amplifier
        ports, _ = self.draw_integ_amp(0, seg_dict, fg_dum=fg_dum)
        vss_warrs, vdd_warrs = self.fill_dummy()

        for name, warr in ports.items():
            self.add_pin(name, warr, show=show_pins)
        self.add_pin('VSS', vss_warrs, show=show_pins)
        self.add_pin('VDD', vdd_warrs, show=show_pins)


class LaygoDummy(LaygoBase):
    """A dummy laygo cell to test AnalogBase-LaygoBase pitch matching.

    Parameters
    ----------
    temp_db : TemplateDB
            the template database.
    lib_name : str
        the layout library name.
    params : Dict[str, Any]
        the parameter values.
    used_names : Set[str]
        a set of already used cell names.
    **kwargs :
        dictionary of optional parameters.  See documentation of
        :class:`bag.layout.template.TemplateBase` for details.
    """

    def __init__(self, temp_db, lib_name, params, used_names, **kwargs):
        # type: (TemplateDB, str, Dict[str, Any], Set[str], **kwargs) -> None
        LaygoBase.__init__(self, temp_db, lib_name, params, used_names, **kwargs)
        self._sch_params = None

    @property
    def sch_params(self):
        # type: () -> Dict[str, Any]
        return self._sch_params

    @classmethod
    def get_params_info(cls):
        # type: () -> Dict[str, str]
        return dict(
            config='laygo configuration dictionary.',
            analog_info='The AnalogBase information dictionary.',
            num_col='Number of laygo olumns.'
        )

    def draw_layout(self):
        analog_info = self.params['analog_info']
        num_col = self.params['num_col']

        if num_col is None:
            raise ValueError('num_col must be a positive integer.')

        self.set_rows_analog(analog_info, num_col=num_col)
        self.fill_space()


def make_tdb(prj, target_lib, specs):
    grid_specs = specs['routing_grid']
    layers = grid_specs['layers']
    widths = grid_specs['widths']
    spaces = grid_specs['spaces']
    bot_dir = grid_specs['bot_dir']
    width_override = grid_specs.get('width_override', None)

    routing_grid = RoutingGrid(prj.tech_info, layers, spaces, widths, bot_dir,
                               width_override=width_override)
    tdb = TemplateDB('template_libs.def', routing_grid, target_lib, use_cybagoa=True)
    return tdb


def generate(prj, specs):
    impl_lib = specs['impl_lib']
    impl_cell = specs['impl_cell']
    params = specs['params']
    laygo_params = specs['laygo_params']

    temp_db = make_tdb(prj, impl_lib, specs)

    name_list = [impl_cell, impl_cell + '_LAYGO']
    temp1 = temp_db.new_template(params=params, temp_cls=IntegAmp, debug=False)

    laygo_params['analog_info'] = temp1.analog_info
    temp2 = temp_db.new_template(params=laygo_params, temp_cls=LaygoDummy, debug=False)

    temp_list = [temp1, temp2]
    print('creating layout')
    temp_db.batch_layout(prj, temp_list, name_list)
    print('layout done')


if __name__ == '__main__':
    with open('specs_test/analog_laygo.yaml', 'r') as f:
        block_specs = yaml.load(f)

    local_dict = locals()
    if 'bprj' not in local_dict:
        print('creating BAG project')
        bprj = BagProject()

    else:
        print('loading BAG project')
        bprj = local_dict['bprj']

    generate(bprj, block_specs)
