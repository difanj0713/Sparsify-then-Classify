from imports import *

warnings.filterwarnings("ignore")
hs_layer_dict = {"distilbert": 7, "roberta": 13, "gpt2-xl": 50, "gpt2": 14, "gpt2-medium": 26, "gpt2-large": 38}
act_layer_dict = {"distilbert": 6, "roberta": 12, "gpt2-xl": 48, "gpt2": 12, "gpt2-medium": 24, "gpt2-large": 36}
pooling_dict = {0: "first_token", 1: "max_pooling", 2: "avg_pooling"}
f1_score_macro = partial(f1_score, average='macro')
metrics_dict = {"imdb": accuracy_score, "edos": f1_score_macro, "sst-2": accuracy_score}

def layer_agg(model_name, is_finetuned, dataset, eta_list, iter_interval=2, max_iter_increment=8):
    if is_finetuned:
        train_pkl = f'../dataset_acts/{dataset}/train_all_{model_name}_finetuned_res.pkl'
        test_pkl = f'../dataset_acts/{dataset}/test_all_{model_name}_finetuned_res.pkl'
        val_pkl = f'../dataset_acts/{dataset}/val_all_{model_name}_finetuned_res.pkl'
        record_dir = f'../dataset_acts/{dataset}/{model_name}_trained_lr_finetuned.pkl'
        clf_output_dir = f'../dataset_acts/{dataset}/new_agg/{model_name}_lr_agg_neurons_clf_finetuned.pkl'
        cumul_dict_dir = f'../dataset_acts/{dataset}/new_agg/{model_name}_lr_agg_neurons_finetuned.pkl'
    else:
        train_pkl = f'../dataset_acts/{dataset}/train_all_{model_name}_res.pkl'
        test_pkl = f'../dataset_acts/{dataset}/test_all_{model_name}_res.pkl'
        val_pkl = f'../dataset_acts/{dataset}/val_all_{model_name}_res.pkl'
        record_dir = f'../dataset_acts/{dataset}/{model_name}_trained_lr.pkl'
        clf_output_dir = f'../dataset_acts/{dataset}/new_agg/{model_name}_lr_agg_neurons_clf.pkl'
        cumul_dict_dir = f'../dataset_acts/{dataset}/new_agg/{model_name}_lr_agg_neurons.pkl'
    
    with open(train_pkl, 'rb') as f:
        train_res = pickle.load(f)
    with open(test_pkl, 'rb') as f:
        test_res = pickle.load(f)
    with open(val_pkl, 'rb') as f:
        val_res = pickle.load(f)
    with open(record_dir, 'rb') as f:
        record = pickle.load(f)

    text_train, text_val, text_test, label_train, label_val, label_test = my_train_test_split(dataset)
    y_train_full = [label_train[i] for i in train_res[0]]
    y_test_full = [label_test[i] for i in test_res[0]]
    y_val_full = [label_val[i] for i in val_res[0]]
    cumul_dict = defaultdict(float)
    clf_dict = defaultdict()

    top_k_flag = False
    #top_k_list = [1, 2, 3, 5, 10, 20, 50, 100, 200, 500, 1000]
    #threshold_list = [0.001, 0.01, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5]

    all_selected_features = []
    aggregated_X_train = torch.empty(0)
    aggregated_X_val = torch.empty(0)
    aggregated_X_test = torch.empty(0)

    for pooling_choice in range(3):
        for threshold in eta_list:
            all_selected_features = []
            aggregated_X_train = torch.empty(0)
            aggregated_X_val = torch.empty(0)
            aggregated_X_test = torch.empty(0)
            for layer in range(hs_layer_dict[model_name]):
                coefficients = record['hs', pooling_choice, layer].coef_[0]
                feature_ids = np.arange(len(coefficients)).tolist()
                importance = coefficients**2
                importance_dict = {feature: sq_imp for feature, sq_imp in zip(feature_ids, importance)}
                sorted_features = sorted(importance_dict.items(), key=lambda x: x[1], reverse=True)
                total_importance = np.sum(importance)

                selected_features = []
                cumulative_importance = 0.0
                layer_count = 0
                for feature, importance in sorted_features:
                    selected_features.append(feature)
                    all_selected_features.append((layer, feature, importance))

                    if top_k_flag:
                        layer_count += 1
                        if layer_count >= top_k:
                            break
                    else:
                        cumulative_importance += importance
                        if cumulative_importance >= threshold * total_importance:
                            break

                X_train_layer = train_res[1][layer,:,selected_features,pooling_choice].detach()
                X_val_layer = val_res[1][layer,:,selected_features,pooling_choice].detach()
                X_test_layer = test_res[1][layer,:,selected_features,pooling_choice].detach()
                aggregated_X_train = torch.cat([aggregated_X_train, X_train_layer], dim=1)
                aggregated_X_val = torch.cat([aggregated_X_val, X_val_layer], dim=1)
                aggregated_X_test = torch.cat([aggregated_X_test , X_test_layer], dim=1)

                #print(len(all_selected_features))

                best_tmp_clf=0
                best_iter=0
                best_val_acc=0
                tmp_clf = LogisticRegression(max_iter=iter_interval, C=0.2, penalty='elasticnet', l1_ratio=1, solver='saga', multi_class='ovr', n_jobs=-1, random_state=42, warm_start=True)

                for i in range(max_iter_increment):
                    tmp_clf.fit(aggregated_X_train, y_train_full)
                    tmp_val_acc = metrics_dict[dataset](y_val_full, tmp_clf.predict(aggregated_X_val))
                    if best_val_acc < tmp_val_acc:
                        best_tmp_clf = tmp_clf
                        best_iter = int((i+1)*iter_interval)
                        best_val_acc = tmp_val_acc

                pooling = pooling_dict[pooling_choice]
                y_pred = best_tmp_clf.predict(aggregated_X_test)
                test_acc = metrics_dict[dataset](y_test_full, y_pred)
                print("First {0} Layers Aggregated Hidden States, Cumulative Ratio {4}, Pooling choice {1}: Performance = {2}, best_iter = {3}".format(layer, pooling, test_acc, best_iter, threshold))
                clf_dict['hs', layer, pooling_choice, threshold, len(all_selected_features)] = best_tmp_clf
                cumul_dict['hs', layer, pooling_choice, threshold, len(all_selected_features), 'test'] = test_acc
                cumul_dict['hs', layer, pooling_choice, threshold, len(all_selected_features), 'val'] = best_val_acc
            
        for threshold in eta_list:
            all_selected_features = []
            aggregated_X_train = torch.empty(0)
            aggregated_X_val = torch.empty(0)
            aggregated_X_test = torch.empty(0)
            for layer in range(act_layer_dict[model_name]):
                coefficients = record['act', pooling_choice, layer].coef_[0]
                feature_ids = np.arange(len(coefficients)).tolist()
                importance = coefficients**2
                importance_dict = {feature: sq_imp for feature, sq_imp in zip(feature_ids, importance)}
                sorted_features = sorted(importance_dict.items(), key=lambda x: x[1], reverse=True)
                total_importance = np.sum(importance)

                selected_features = []
                cumulative_importance = 0.0
                layer_count = 0
                for feature, importance in sorted_features:
                    selected_features.append(feature)
                    all_selected_features.append((layer, feature, importance))

                    if top_k_flag:
                        layer_count += 1
                        if layer_count >= top_k:
                            break
                    else:
                        cumulative_importance += importance
                        if cumulative_importance >= threshold * total_importance:
                            break

                X_train_layer = train_res[2][layer,:,selected_features,pooling_choice].detach()
                X_val_layer = val_res[2][layer,:,selected_features,pooling_choice].detach()
                X_test_layer = test_res[2][layer,:,selected_features,pooling_choice].detach()
                aggregated_X_train = torch.cat([aggregated_X_train, X_train_layer], dim=1)
                aggregated_X_val = torch.cat([aggregated_X_val, X_val_layer], dim=1)
                aggregated_X_test = torch.cat([aggregated_X_test , X_test_layer], dim=1)

                #print(len(all_selected_features))

                best_tmp_clf=0
                best_iter=0
                best_val_acc=0
                tmp_clf = LogisticRegression(max_iter=iter_interval, C=0.2, penalty='elasticnet', l1_ratio=1, solver='saga', multi_class='ovr', n_jobs=-1, random_state=42, warm_start=True)

                for i in range(max_iter_increment):
                    tmp_clf.fit(aggregated_X_train, y_train_full)
                    tmp_val_acc = metrics_dict[dataset](y_val_full, tmp_clf.predict(aggregated_X_val))
                    if best_val_acc < tmp_val_acc:
                        best_tmp_clf = tmp_clf
                        best_iter = int((i+1)*iter_interval)
                        best_val_acc = tmp_val_acc

                pooling = pooling_dict[pooling_choice]
                y_pred = best_tmp_clf.predict(aggregated_X_test)
                test_acc = metrics_dict[dataset](y_test_full, y_pred)
                print("First {0} Layers Aggregated Activations, Cumulative Ratio {4}, Pooling choice {1}: Performance = {2}, best_iter = {3}".format(layer, pooling, test_acc, best_iter, threshold))
                clf_dict['act', layer, pooling_choice, threshold, len(all_selected_features)] = best_tmp_clf
                cumul_dict['act', layer, pooling_choice, threshold, len(all_selected_features), 'test'] = test_acc
                cumul_dict['act', layer, pooling_choice, threshold, len(all_selected_features), 'val'] = best_val_acc

    max_k = 0
    max_v = 0
    for key, value in cumul_dict.items():
        if value > max_v and key[-1] == 'test':
            max_k = key
            max_v = value
    (rep, l, p, eta, n, _)= max_k
    test_max_k = (rep, l, p, eta, n, 'test')
    print("Final STC performance: ", cumul_dict[test_max_k])
    with open(cumul_dict_dir, 'wb') as f:
        pickle.dump(cumul_dict, f)
    with open(clf_dict_dir, 'wb') as f:
        pickle.dump(clf_dict, f)

def main() -> None:
    parser = argparse.ArgumentParser(description='Initialize analysis for specified model and dataset.')
    parser.add_argument('--model_name', type=str, required=True, 
                        help='The name of the model. Options: distilbert, roberta, gpt2-base, gpt2-medium, gpt2-large, gpt2-xl')
    parser.add_argument('--dataset', type=str, required=True, 
                        help='The name of the dataset. Options: imdb, edos, sst-2')
    parser.add_argument('--is_finetuned', type=int, required=True,
                        help='Flag for finetuned models. Options: 1 for finetuned, 0 for frozen')
    args = parser.parse_args()

    eta_list = threshold_list = [0.001, 0.01, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5] # hyperparam as how many cumsum weights to be selected per layer.
    layer_agg(args.model_name, args.is_finetuned, args.dataset, eta_list, iter_interval=2, max_iter_increment=16)

if __name__ == "__main__":
    main()