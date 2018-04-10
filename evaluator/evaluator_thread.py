import logging
import threading

from config.cst import *
from evaluator.Updaters.social_evaluator_not_threaded_update import SocialEvaluatorNotThreadedUpdateThread
from evaluator.Updaters.time_frame_update import TimeFrameUpdateDataThread
from evaluator.evaluator import Evaluator


class EvaluatorThread(threading.Thread):
    def __init__(self, config,
                 symbol,
                 time_frame,
                 matrix,
                 exchange,
                 notifier,
                 social_eval_list,
                 real_time_TA_eval_list,
                 trader,
                 simulator):
        threading.Thread.__init__(self)
        self.config = config
        self.symbol = symbol
        self.time_frame = time_frame

        # Exchange
        self.exchange = exchange
        # self.exchange.update_balance(self.symbol)

        # Notifer
        self.notifier = notifier

        # Trader
        self.trader = trader
        self.simulator = simulator

        self.matrix = matrix

        self.thread_name = "TA THREAD - " + self.symbol \
                           + " - " + self.exchange.__class__.__name__ \
                           + " - " + str(self.time_frame)
        self.logger = logging.getLogger(self.thread_name)

        # Create Evaluator
        self.evaluator = Evaluator()
        self.evaluator.set_config(self.config)
        self.evaluator.set_symbol(self.symbol)
        self.evaluator.set_time_frame(self.time_frame)
        self.evaluator.set_notifier(self.notifier)
        self.evaluator.set_trader(self.trader)
        self.evaluator.set_trader_simulator(self.simulator)
        self.evaluator.set_exchange(self.exchange)

        # Add threaded evaluators that can notify the current thread
        self.evaluator.get_creator().set_social_eval(social_eval_list, self)
        self.evaluator.get_creator().set_real_time_eval(real_time_TA_eval_list, self)

        # Create refreshing threads
        self.data_refresher = TimeFrameUpdateDataThread(self)
        self.social_evaluator_refresh = SocialEvaluatorNotThreadedUpdateThread(self)

    def notify(self, notifier_name):
        if self.data_refresher.get_refreshed_times() > 0:
            self.logger.debug("** Notified by " + notifier_name + " **")
            self.refresh_eval(notifier_name)
        else:
            self.logger.debug("Notification by " + notifier_name + " ignored")

    def refresh_eval(self, ignored_evaluator=None):
        # Instances will be created only if they don't already exist
        self.evaluator.get_creator().create_ta_eval_list()
        self.evaluator.get_creator().create_strategies_eval_list()

        # update eval
        self.evaluator.update_ta_eval(ignored_evaluator)

        # update matrix
        self.refresh_matrix()

        # update strategies matrix
        self.evaluator.update_strategies_eval(self.matrix, ignored_evaluator)

        # use matrix
        for strategies_eval in self.evaluator.get_creator().get_strategies_eval_list():
            self.matrix.set_eval(EvaluatorMatrixTypes.STRATEGIES, strategies_eval.get_name(),
                                 strategies_eval.get_eval_note())

        # calculate the final result
        self.evaluator.finalize()
        self.logger.debug("--> " + str(self.evaluator.get_final().get_state()))
        self.logger.debug("MATRIX : " + str(self.matrix.get_matrix()))

    def refresh_matrix(self):
        for ta_eval in self.evaluator.get_creator().get_ta_eval_list():
            self.matrix.set_eval(EvaluatorMatrixTypes.TA, ta_eval.get_name(),
                                 ta_eval.get_eval_note(), self.time_frame)

        for social_eval in self.evaluator.get_creator().get_social_eval_list():
            self.matrix.set_eval(EvaluatorMatrixTypes.SOCIAL, social_eval.get_name(),
                                 social_eval.get_eval_note())

        for real_time_eval in self.evaluator.get_creator().get_real_time_eval_list():
            self.matrix.set_eval(EvaluatorMatrixTypes.REAL_TIME, real_time_eval.get_name(),
                                 real_time_eval.get_eval_note())

    def run(self):
        # Start refresh threads
        self.data_refresher.start()
        self.social_evaluator_refresh.start()
        self.data_refresher.join()
        self.social_evaluator_refresh.join()

    def stop(self):
        for thread in self.evaluator.get_creator().get_social_eval_list():
            thread.stop()
        for thread in self.evaluator.get_creator().get_real_time_eval_list():
            thread.stop()
        self.data_refresher.stop()
        self.social_evaluator_refresh.stop()
