from pathos.multiprocessing import ProcessingPool as Pool

from cadCAD.utils import flatten
from cadCAD.configuration import Processor
from cadCAD.configuration.utils import TensorFieldReport
from cadCAD.engine.simulation import Executor as SimExecutor


class ExecutionMode:
    single_proc = 'single_proc'
    multi_proc = 'multi_proc'


class ExecutionContext:
    def __init__(self, context=ExecutionMode.multi_proc):
        self.name = context
        self.method = None

        def single_proc_exec(simulation_execs, var_dict, states_lists, configs_structs, env_processes_list, Ts, Ns):
            l = [simulation_execs, states_lists, configs_structs, env_processes_list, Ts, Ns]
            simulation, states_list, config, env_processes, T, N = list(map(lambda x: x.pop(), l))
            result = simulation(var_dict, states_list, config, env_processes, T, N)
            return flatten(result)

        def parallelize_simulations(simulations, var_dict_list, states_list, configs, env_processes, Ts, Ns):
            l = list(zip(simulations, var_dict_list, states_list, configs, env_processes, Ts, Ns))
            with Pool(len(configs)) as p:
                results = p.map(lambda t: t[0](t[1], t[2], t[3], t[4], t[5], t[6]), l)
            return results

        if context == 'single_proc':
            self.method = single_proc_exec
        elif context == 'multi_proc':
            self.method = parallelize_simulations


class Executor:
    def __init__(self, exec_context, configs):
        self.SimExecutor = SimExecutor
        self.exec_method = exec_context.method
        self.exec_context = exec_context.name
        self.configs = configs
        self.main = self.execute

    def execute(self):
        config_proc = Processor()
        create_tensor_field = TensorFieldReport(config_proc).create_tensor_field

        print(self.exec_context+": "+str(self.configs))
        var_dict_list, states_lists, Ts, Ns, eps, configs_structs, env_processes_list, partial_state_updates, simulation_execs = \
            [], [], [], [], [], [], [], [], []
        config_idx = 0
        for x in self.configs:

            Ts.append(x.sim_config['T'])
            Ns.append(x.sim_config['N'])
            var_dict_list.append(x.sim_config['M'])
            states_lists.append([x.initial_state])
            eps.append(list(x.exogenous_states.values()))
            configs_structs.append(config_proc.generate_config(x.initial_state, x.partial_state_updates, eps[config_idx]))
            env_processes_list.append(x.env_processes)
            partial_state_updates.append(x.partial_state_updates)
            simulation_execs.append(SimExecutor(x.policy_ops).simulation)

            config_idx += 1

        if self.exec_context == ExecutionMode.single_proc:
            # ToDO: Deprication Handler - "sanitize" in appropriate place
            tensor_field = create_tensor_field(partial_state_updates.pop(), eps.pop())
            result = self.exec_method(simulation_execs, var_dict_list, states_lists, configs_structs, env_processes_list, Ts, Ns)
            return result, tensor_field
        elif self.exec_context == ExecutionMode.multi_proc:
            if len(self.configs) > 1:
                simulations = self.exec_method(simulation_execs, var_dict_list, states_lists, configs_structs, env_processes_list, Ts, Ns)
                results = []
                for result, partial_state_updates, ep in list(zip(simulations, partial_state_updates, eps)):
                    results.append((flatten(result), create_tensor_field(partial_state_updates, ep)))

                return results