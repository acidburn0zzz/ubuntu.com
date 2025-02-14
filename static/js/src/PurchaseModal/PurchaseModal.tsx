import React, { useEffect, useState } from "react";
import * as Sentry from "@sentry/react";
import useStripeCustomerInfo from "./hooks/useStripeCustomerInfo";
import registerPaymentMethod from "./hooks/registerPaymentMethod";
import { Formik, FormikHelpers } from "formik";
import { useQueryClient } from "react-query";
import { getErrorMessage } from "../advantage/error-handler";
import { checkoutEvent } from "../advantage/ecom-events";
import {
  getUserInfoFromVariables,
  getInitialFormValues,
  FormValues,
  marketplace,
} from "./utils/utils";
import StepOne from "./components/ModalSteps/StepOne";
import StepTwo from "./components/ModalSteps/StepTwo";
import { BuyButtonProps } from "./utils/utils";
type Props = {
  termsLabel: React.ReactNode;
  product: any;
  preview: any;
  quantity: number;
  closeModal: () => void;
  Summary: React.ComponentType;
  BuyButton: React.ComponentType<BuyButtonProps>;
  marketplace: marketplace;
};

const PurchaseModal = ({
  termsLabel,
  product,
  preview,
  quantity,
  closeModal,
  Summary,
  BuyButton,
  marketplace,
}: Props) => {
  const [error, setError] = useState<React.ReactNode>(null);
  const { data: userInfo } = useStripeCustomerInfo();
  const [step, setStep] = useState(
    userInfo?.customerInfo?.defaultPaymentMethod ? 2 : 1
  );
  const queryClient = useQueryClient();

  const paymentMethodMutation = registerPaymentMethod();

  const initialValues = getInitialFormValues(userInfo, window.accountId);

  useEffect(() => {
    if (userInfo?.customerInfo?.defaultPaymentMethod) {
      setStep(2);
    }
  }, [userInfo]);

  const GAFriendlyProduct = {
    id: product?.id,
    name: product?.name,
    price: product?.price?.value / 100,
    quantity: quantity,
  };

  const onSubmit = (values: FormValues, actions: FormikHelpers<FormValues>) => {
    setError(null);
    checkoutEvent(GAFriendlyProduct, "2");
    paymentMethodMutation.mutate(
      { formData: values, marketplace: marketplace },
      {
        onSuccess: (data, variables) => {
          window.accountId = data.accountId;
          setStep(2);
          queryClient.setQueryData(
            "userInfo",
            getUserInfoFromVariables(data, variables.formData)
          );
          queryClient.invalidateQueries("preview");

          actions.setSubmitting(false);
        },
        onError: (error) => {
          if (error instanceof Error)
            if (error.message === "email_already_exists") {
              setError(
                <>
                  An Ubuntu One account with this email address exists. Please{" "}
                  <a href="/login">sign in</a> to your account first.
                </>
              );
            } else {
              const knownErrorMessage = getErrorMessage({
                message: "",
                code: error.message,
              });

              // Tries to match the error with a known error code and defaults to a generic error if it fails
              if (knownErrorMessage) {
                setError(knownErrorMessage);
              } else {
                Sentry.captureException(error);
                setError(
                  <>
                    Sorry, there was an unknown error with your credit card.
                    Check the details and try again. Contact{" "}
                    <a href="https://ubuntu.com/contact-us">Canonical sales</a>{" "}
                    if the problem persists.
                  </>
                );
              }
            }

          actions.setSubmitting(false);
        },
      }
    );
  };

  return (
    <Formik
      initialValues={initialValues}
      enableReinitialize={true}
      onSubmit={onSubmit}
    >
      <>
        {step === 1 ? (
          <StepOne error={error} closeModal={closeModal} />
        ) : (
          <StepTwo
            termsLabel={termsLabel}
            setStep={setStep}
            error={error}
            setError={setError}
            Summary={Summary}
            closeModal={closeModal}
            product={product}
            preview={preview}
            BuyButton={BuyButton}
          />
        )}
      </>
    </Formik>
  );
};

export default PurchaseModal;
